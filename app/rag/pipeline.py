"""Retrieval Pipeline：Query -> BM25+Dense -> Fusion -> Reranker -> Evidence。

这是"Knowledge Retrieval Tool"内部的完整引擎，设计成可以脱离 Agent 独立调用/独立
评测（eval/run_eval.py 直接用这个类，不经过 Agent Loop），对应架构文档里
"RAG和Agent分别能独立讲清楚"的边界要求。
"""
import time
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from app.core.embedder import Embedder
from app.core.types import Chunk, Evidence, ScoredChunk
from app.rag.context_builder import build_evidence
from app.rag.reranker import Reranker
from app.rag.retriever.dense import DenseRetriever
from app.rag.retriever.hybrid import reciprocal_rank_fusion
from app.rag.retriever.sparse import SparseRetriever


@dataclass
class RetrievalDebugInfo:
    query: str
    rewritten_query: str | None
    bm25_candidates: list[dict] = field(default_factory=list)
    dense_candidates: list[dict] = field(default_factory=list)
    fusion_candidates: list[dict] = field(default_factory=list)
    rerank_candidates: list[dict] = field(default_factory=list)
    latency_breakdown: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievalOutput:
    evidence: list[Evidence]
    debug: RetrievalDebugInfo


def _to_dict_list(scored: list[ScoredChunk]) -> list[dict]:
    return [{"chunk_id": s.chunk.id, "score": round(s.score, 6), "rank": s.rank} for s in scored]


class RetrievalPipeline:
    def __init__(self, session: Session, embedder: Embedder, reranker: Reranker, all_chunks: list[Chunk]):
        self.session = session
        self.dense = DenseRetriever(session, embedder)
        self.sparse = SparseRetriever(all_chunks)
        self.reranker = reranker

    def retrieve(
        self, query: str, top_k_candidate: int = 30, top_k_final: int = 5, doc_titles: dict[str, str] | None = None
    ) -> RetrievalOutput:
        doc_titles = doc_titles or {}
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
        return RetrievalOutput(evidence=evidence, debug=debug)
