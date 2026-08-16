"""数据灌入脚本：data/raw/*.md -> 清洗(读取) -> Chunk -> Embedding -> pgvector。

幂等：每次运行先清空 documents/document_chunks 再重新灌入，方便反复调整
chunk_size/overlap 参数重跑实验（对应 architecture.md 里的 Chunking 实验）。

用法：
  python scripts/ingest.py                       # 默认 chunk_size=512, overlap=50
  python scripts/ingest.py --chunk-size 256       # 用于对比实验
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.embedder import get_embedder  # noqa: E402
from app.db.models import Document, DocumentChunk, KnowledgeSource  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.rag.chunking import chunk_markdown  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def ingest(chunk_size: int = 512, overlap: int = 50) -> dict:
    init_db()
    session = SessionLocal()
    embedder = get_embedder()

    try:
        session.query(DocumentChunk).delete()
        session.query(Document).delete()
        session.query(KnowledgeSource).delete()
        session.commit()

        source = KnowledgeSource(name="mock_enterprise_docs", source_type="doc")
        session.add(source)
        session.flush()

        total_chunks = 0
        doc_paths = sorted(RAW_DIR.glob("*.md"))
        for path in doc_paths:
            raw = path.read_text(encoding="utf-8")
            title = raw.splitlines()[0].lstrip("# ").strip() if raw else path.stem
            doc = Document(
                source_id=source.id, title=title, raw_content=raw,
                doc_metadata={"slug": path.stem}, version=1,
            )
            session.add(doc)
            session.flush()

            raw_chunks = chunk_markdown(raw, chunk_size=chunk_size, overlap=overlap)
            if not raw_chunks:
                continue
            embeddings = embedder.embed([c.content for c in raw_chunks])

            for rc, emb in zip(raw_chunks, embeddings):
                session.add(
                    DocumentChunk(
                        document_id=doc.id, chunk_index=rc.chunk_index, content=rc.content,
                        embedding=emb,
                        chunk_metadata={"slug": path.stem, "section_title": rc.section_title, "title": title},
                        embedding_version=1,
                    )
                )
            total_chunks += len(raw_chunks)
            print(f"  ingested {path.name}: {len(raw_chunks)} chunks")

        session.commit()
        return {"documents": len(doc_paths), "chunks": total_chunks, "chunk_size": chunk_size, "overlap": overlap}
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=50)
    args = parser.parse_args()
    stats = ingest(chunk_size=args.chunk_size, overlap=args.overlap)
    print(f"Ingest done: {stats}")
