"""Run only the V2 100-case retrieval baseline (no LLM calls)."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.embedder import get_embedder
from app.rag.reranker import get_reranker
from scripts.offline_demo import build_pipeline, load_and_chunk, run_retrieval_eval


def main():
    chunks, _ = load_and_chunk()
    started = time.perf_counter()
    pipeline = build_pipeline(chunks, get_embedder(), get_reranker())
    load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    report = run_retrieval_eval(pipeline, chunks)
    eval_ms = (time.perf_counter() - started) * 1000
    result = {
        "run_at": datetime.now(timezone.utc).isoformat(), "cases": 100,
        "documents": 25, "chunks": len(chunks), "model_and_index_load_ms": load_ms,
        "evaluation_ms": eval_ms, "metrics": report,
    }
    output = Path("eval/results") / f"v2_retrieval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
