"""Measure cold vs repeated retrieval latency and save an auditable result."""
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.embedder import get_embedder
from app.rag.reranker import get_reranker
from scripts.offline_demo import build_pipeline, load_and_chunk


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))]


def build_benchmark_result(chunks, cold: list[float], warm: list[float], run_at: str) -> dict:
    return {
        "run_at": run_at,
        "documents": len({chunk.document_id for chunk in chunks}),
        "chunks": len(chunks),
        "cold_ms": {"mean": statistics.mean(cold), "p95": percentile(cold, .95)},
        "warm_ms": {"mean": statistics.mean(warm), "p95": percentile(warm, .95)},
        "note": "Model loading is excluded; warm measurements are exact-query in-process cache hits.",
    }


def main():
    chunks, _ = load_and_chunk()
    pipeline = build_pipeline(chunks, get_embedder(), get_reranker())
    queries = ["订单服务502怎么排查", "Redis热Key怎么定位", "Pod一直Pending怎么办"]
    cold, warm = [], []
    for query in queries:
        start = time.perf_counter(); pipeline.retrieve(query); cold.append((time.perf_counter() - start) * 1000)
        for _ in range(5):
            start = time.perf_counter(); pipeline.retrieve(query); warm.append((time.perf_counter() - start) * 1000)
    result = build_benchmark_result(
        chunks, cold, warm, datetime.now(timezone.utc).isoformat()
    )
    output = Path("eval/results") / f"retrieval_benchmark_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
