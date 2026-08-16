"""Dense 检索：pgvector cosine similarity。

用 `<=>`（cosine distance）算子直接在数据库里排序，不把全部向量拉到应用层
再用numpy算——数据量大起来时这是关键的性能分界点（对应架构文档里
"pgvector实测P95延迟超阈值再考虑Milvus"这条ADR的判断依据之一）。
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.embedder import Embedder
from app.core.types import Chunk, ScoredChunk


class DenseRetriever:
    def __init__(self, session: Session, embedder: Embedder):
        self.session = session
        self.embedder = embedder

    def search(self, query: str, top_k: int = 30) -> list[ScoredChunk]:
        query_vec = self.embedder.embed_one(query)
        vec_literal = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"
        sql = text(
            """
            SELECT id, document_id, content, metadata,
                   1 - (embedding <=> CAST(:qvec AS vector)) AS score
            FROM document_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:qvec AS vector)
            LIMIT :top_k
            """
        )
        rows = self.session.execute(sql, {"qvec": vec_literal, "top_k": top_k}).fetchall()
        results = []
        for i, row in enumerate(rows):
            chunk = Chunk(
                id=str(row.id), document_id=str(row.document_id), content=row.content, metadata=row.metadata or {}
            )
            results.append(ScoredChunk(chunk=chunk, score=float(row.score), rank=i + 1))
        return results
