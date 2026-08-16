from app.core.types import Chunk, ScoredChunk
from app.rag.retriever.hybrid import reciprocal_rank_fusion


def _sc(chunk_id: str, rank: int, score: float = 1.0) -> ScoredChunk:
    return ScoredChunk(chunk=Chunk(id=chunk_id, document_id="doc1", content=f"content {chunk_id}"), score=score, rank=rank)


def test_fusion_favors_doc_ranked_high_in_both_lists():
    bm25 = [_sc("A", 1), _sc("B", 2), _sc("C", 3)]
    dense = [_sc("A", 1), _sc("C", 2), _sc("B", 3)]
    fused = reciprocal_rank_fusion([bm25, dense], k=60, top_k=10)
    assert fused[0].chunk.id == "A"  # 两路都排第一，融合后必须仍是第一


def test_fusion_includes_doc_found_by_only_one_retriever():
    bm25 = [_sc("A", 1)]
    dense = [_sc("B", 1)]
    fused = reciprocal_rank_fusion([bm25, dense], k=60, top_k=10)
    ids = {sc.chunk.id for sc in fused}
    assert ids == {"A", "B"}  # 任一路召回到的都应该出现在候选池里，这是Hybrid互补性的核心


def test_fusion_respects_top_k():
    bm25 = [_sc(str(i), i) for i in range(1, 11)]
    fused = reciprocal_rank_fusion([bm25], k=60, top_k=3)
    assert len(fused) == 3


def test_fusion_empty_lists_returns_empty():
    assert reciprocal_rank_fusion([[], []], top_k=10) == []
