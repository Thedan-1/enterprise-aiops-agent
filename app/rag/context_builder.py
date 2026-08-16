"""Context Builder：把精排后的 Chunk 转成 Evidence（带引用），并做长度截断。

截断而不是把所有候选都塞给LLM的原因：不是"越多context效果越好"——
无关内容(noise)会稀释LLM对真正相关证据的注意力，也直接增加token成本。
"""
from app.core.types import Evidence, ScoredChunk

MAX_TOTAL_CHARS = 4000


def build_evidence(scored_chunks: list[ScoredChunk], doc_titles: dict[str, str]) -> list[Evidence]:
    evidence = []
    total_chars = 0
    for sc in scored_chunks:
        source = doc_titles.get(sc.chunk.document_id, sc.chunk.metadata.get("title", "未知来源"))
        content = sc.chunk.content
        if total_chars + len(content) > MAX_TOTAL_CHARS:
            remaining = MAX_TOTAL_CHARS - total_chars
            if remaining <= 0:
                break
            content = content[:remaining]
        evidence.append(Evidence(chunk_id=sc.chunk.id, content=content, source=source, score=sc.score))
        total_chars += len(content)
        if total_chars >= MAX_TOTAL_CHARS:
            break
    return evidence
