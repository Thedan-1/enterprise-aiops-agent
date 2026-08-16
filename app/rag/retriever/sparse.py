"""BM25 稀疏检索。

实现说明（MVP简化，需在面试时如实说明）：架构设计里写的是 Postgres tsvector+GIN，
但 tsvector 的中文分词支持较弱且配置复杂，MVP 用 rank_bm25 做进程内索引，
接口保持独立可替换，数据规模大到需要持久化索引/分布式检索时再迁移到
Postgres tsvector 或 Elasticsearch（对应 architecture.md ADR）。

中文分词：没有引入 jieba 等分词器（避免额外的模型/词典依赖），用字符 bigram
近似分词。这是已知的精度损失点——专业术语（如"连接池"）会被切成"连接池"的
bigram集合而不是一个完整词，这正是 project_management.md 故障排查树里
"BM25中文分词切碎术语"这一条的具体来源，用真实分词器是明确的改进方向。
"""
import re

from rank_bm25 import BM25Okapi

from app.core.types import Chunk, ScoredChunk


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = re.findall(r"[a-z0-9]+", text)
    cjk = re.findall(r"[一-鿿]+", text)
    for seg in cjk:
        if len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
    return tokens


class SparseRetriever:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._corpus_tokens = [tokenize(c.content) for c in chunks]
        self._bm25 = BM25Okapi(self._corpus_tokens) if chunks else None

    def search(self, query: str, top_k: int = 30) -> list[ScoredChunk]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self.chunks, scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            ScoredChunk(chunk=c, score=float(s), rank=i + 1)
            for i, (c, s) in enumerate(ranked)
            if s > 0
        ]
