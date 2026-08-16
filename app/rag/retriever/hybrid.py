"""Hybrid Retrieval：Reciprocal Rank Fusion (RRF)。

选RRF而不是"归一化后线性加权"的原因：BM25分数和Cosine相似度分数的量纲完全不同
（BM25无上界，Cosine在[-1,1]），线性加权需要先做min-max归一化，且权重是一个
要调的超参数；RRF只依赖排名（rank），不依赖原始分数的量纲，对两路检索器的
分数分布差异天然鲁棒，是业界（如Elasticsearch/Weaviate）hybrid search的常用默认方案。

score(chunk) = sum_over_retrievers( 1 / (k + rank) )，k默认60（RRF论文经验值，
k越大排名靠后的文档贡献越平滑）。
"""
from app.core.types import ScoredChunk


def reciprocal_rank_fusion(
    result_lists: list[list[ScoredChunk]], k: int = 60, top_k: int = 30
) -> list[ScoredChunk]:
    fused_scores: dict[str, float] = {}
    chunk_by_id = {}
    per_retriever_rank: dict[str, list[int]] = {}

    for results in result_lists:
        for sc in results:
            cid = sc.chunk.id
            chunk_by_id[cid] = sc.chunk
            fused_scores[cid] = fused_scores.get(cid, 0.0) + 1.0 / (k + sc.rank)
            per_retriever_rank.setdefault(cid, []).append(sc.rank)

    ranked_ids = sorted(fused_scores.keys(), key=lambda cid: fused_scores[cid], reverse=True)[:top_k]
    return [
        ScoredChunk(chunk=chunk_by_id[cid], score=fused_scores[cid], rank=i + 1)
        for i, cid in enumerate(ranked_ids)
    ]
