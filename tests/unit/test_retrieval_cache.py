from app.core.types import Chunk, ScoredChunk
from app.rag.pipeline import RetrievalPipeline
from app.rag.reranker import NoOpReranker


class CountingSearcher:
    def __init__(self, chunk):
        self.chunk = chunk
        self.calls = 0

    def search(self, query, top_k):
        self.calls += 1
        return [ScoredChunk(self.chunk, 1.0, 1)]


def test_repeated_retrieval_uses_cache():
    chunk = Chunk("c1", "d1", "订单服务502排查", {"title": "runbook"})
    dense = CountingSearcher(chunk)
    sparse = CountingSearcher(chunk)
    pipeline = RetrievalPipeline(dense, sparse, NoOpReranker())
    first = pipeline.retrieve("502")
    second = pipeline.retrieve("502")
    assert first.debug.cache_hit is False
    assert second.debug.cache_hit is True
    assert dense.calls == sparse.calls == 1


def test_different_query_does_not_share_cache():
    chunk = Chunk("c1", "d1", "content", {})
    dense = CountingSearcher(chunk)
    sparse = CountingSearcher(chunk)
    pipeline = RetrievalPipeline(dense, sparse, NoOpReranker())
    pipeline.retrieve("502")
    pipeline.retrieve("504")
    assert dense.calls == sparse.calls == 2
