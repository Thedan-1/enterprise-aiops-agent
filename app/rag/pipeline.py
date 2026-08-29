"""Retrieval Pipeline：Query -> BM25+Dense -> Fusion -> Reranker -> Evidence。

这是"Knowledge Retrieval Tool"内部的完整引擎，设计成可以脱离 Agent 独立调用/独立
评测（eval/run_eval.py 直接用这个类，不经过 Agent Loop），对应架构文档里
"RAG和Agent分别能独立讲清楚"的边界要求。
"""
import time
import threading
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Protocol

from app.core.types import Evidence, ScoredChunk
from app.rag.context_builder import build_evidence
from app.rag.reranker import Reranker
from app.rag.retriever.hybrid import reciprocal_rank_fusion


class DenseSearcher(Protocol):
    def search(self, query: str, top_k: int) -> list[ScoredChunk]: ...


class SparseSearcher(Protocol):
    def search(self, query: str, top_k: int) -> list[ScoredChunk]: ...


@dataclass
class RetrievalDebugInfo:
    query: str
    rewritten_query: str | None
    bm25_candidates: list[dict] = field(default_factory=list)
    dense_candidates: list[dict] = field(default_factory=list)
    fusion_candidates: list[dict] = field(default_factory=list)
    rerank_candidates: list[dict] = field(default_factory=list)
    latency_breakdown: dict[str, float] = field(default_factory=dict)
    cache_hit: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievalOutput:
    evidence: list[Evidence]
    debug: RetrievalDebugInfo


def _to_dict_list(scored: list[ScoredChunk]) -> list[dict]:
    return [{"chunk_id": s.chunk.id, "score": round(s.score, 6), "rank": s.rank} for s in scored]


class RetrievalPipeline:
    """Dense/Sparse 检索器通过依赖注入传入，Pipeline本身不关心它们是连Postgres
    还是纯内存实现——这样生产环境(DenseRetriever+pgvector)和离线开发/测试环境
    (InMemoryDenseRetriever)可以复用完全相同的Fusion/Rerank/Evidence逻辑，
    只在最外层(runtime_factory.py / scripts/offline_demo.py)决定注入哪一个。
    """

    def __init__(
        self,
        dense_retriever: DenseSearcher,
        sparse_retriever: SparseSearcher,
        reranker: Reranker,
        cache_size: int = 128,
        cache_ttl_s: float = 300.0,
    ):
        self.dense = dense_retriever
        self.sparse = sparse_retriever
        self.reranker = reranker
        self.cache_size = cache_size
        self.cache_ttl_s = cache_ttl_s
        self._cache: OrderedDict[tuple, tuple[float, RetrievalOutput]] = OrderedDict()
        self._cache_lock = threading.Lock()

    def retrieve(
        self, query: str, top_k_candidate: int = 30, top_k_final: int = 5, doc_titles: dict[str, str] | None = None
    ) -> RetrievalOutput:
        doc_titles = doc_titles or {}
        cache_key = (query.strip(), top_k_candidate, top_k_final)
        cached = self._cache_get(cache_key)
        if cached is not None:
            cached.debug.cache_hit = True
            cached.debug.latency_breakdown["cache_lookup_ms"] = 0.0
            return cached
        latency: dict[str, float] = {}

        t0 = time.perf_counter()
        bm25_results = self.sparse.search(query, top_k=top_k_candidate)
        latency["bm25_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        dense_results = self.dense.search(query, top_k=top_k_candidate)
        latency["dense_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        fused = reciprocal_rank_fusion([bm25_results, dense_results], top_k=top_k_candidate)
        latency["fusion_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        reranked = self.reranker.rerank(query, fused, top_k=top_k_final)
        latency["rerank_ms"] = (time.perf_counter() - t0) * 1000

        evidence = build_evidence(reranked, doc_titles)

        debug = RetrievalDebugInfo(
            query=query,
            rewritten_query=None,
            bm25_candidates=_to_dict_list(bm25_results),
            dense_candidates=_to_dict_list(dense_results),
            fusion_candidates=_to_dict_list(fused),
            rerank_candidates=_to_dict_list(reranked),
            latency_breakdown=latency,
        )
        output = RetrievalOutput(evidence=evidence, debug=debug)
        self._cache_put(cache_key, output)
        return output

    def _cache_get(self, key: tuple) -> RetrievalOutput | None:
        now = time.monotonic()
        with self._cache_lock:
            item = self._cache.get(key)
            if item is None:
                return None
            created_at, output = item
            if now - created_at > self.cache_ttl_s:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return deepcopy(output)

    def _cache_put(self, key: tuple, output: RetrievalOutput) -> None:
        if self.cache_size <= 0:
            return
        with self._cache_lock:
            self._cache[key] = (time.monotonic(), deepcopy(output))
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
