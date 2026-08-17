"""Reranker：对 Fusion 阶段的候选池做精排。

为什么不直接让 Retriever 输出 Top5：Retriever（尤其Dense）优化目标是"尽量不漏掉
相关文档"（高Recall），代价是排序不够精细；Reranker 用更贵但更精确的相关性打分
模型（真实实现通常是Cross-Encoder：把query和document拼在一起同时编码，
而不是分别编码再算相似度，因此能捕捉更细粒度的交互特征，但计算成本随候选数量
线性增长，不能对全库使用，只能对Retriever缩小后的候选池使用）重新排序，
用可控的计算成本把Precision提上去。这就是"Retriever广撒网、Reranker精筛选"
的分工依据。

默认 Provider = heuristic：用词面重合度做近似打分，不依赖模型下载。
真实实现应替换为 Cross-Encoder（如 bge-reranker-base），接口不变。
"""
from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.types import ScoredChunk
from app.rag.retriever.sparse import tokenize


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]: ...


class HeuristicReranker(Reranker):
    """词面重合度(Jaccard近似) 与 Fusion阶段分数的加权组合，作为Cross-Encoder的占位替代。"""

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        if not candidates:
            return []
        query_tokens = set(tokenize(query))
        max_fusion_score = max((c.score for c in candidates), default=1.0) or 1.0

        rescored = []
        for sc in candidates:
            doc_tokens = set(tokenize(sc.chunk.content))
            overlap = len(query_tokens & doc_tokens) / (len(query_tokens) or 1)
            normalized_fusion = sc.score / max_fusion_score
            new_score = 0.6 * overlap + 0.4 * normalized_fusion
            rescored.append((sc.chunk, new_score))

        rescored.sort(key=lambda x: x[1], reverse=True)
        return [
            ScoredChunk(chunk=chunk, score=score, rank=i + 1)
            for i, (chunk, score) in enumerate(rescored[:top_k])
        ]


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        from sentence_transformers import CrossEncoder  # lazy import，未安装时不影响默认路径

        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        pairs = [(query, c.chunk.content) for c in candidates]
        scores = self.model.predict(pairs)
        rescored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            ScoredChunk(chunk=sc.chunk, score=float(s), rank=i + 1) for i, (sc, s) in enumerate(rescored)
        ]


class NoOpReranker(Reranker):
    """直接取Fusion阶段的Top-K，不做二次排序——作为"有没有Reranker"这组对比实验的
    对照组，不用于生产（生产默认走HeuristicReranker/CrossEncoderReranker）。"""

    def rerank(self, query: str, candidates: list[ScoredChunk], top_k: int = 5) -> list[ScoredChunk]:
        return candidates[:top_k]


def get_reranker() -> Reranker:
    if settings.reranker_provider == "cross_encoder":
        return CrossEncoderReranker()
    return HeuristicReranker()
