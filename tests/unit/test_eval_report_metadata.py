from app.core.types import Chunk
from scripts.run_v2_retrieval_eval import build_result
from scripts.benchmark_retrieval import build_benchmark_result


def test_eval_report_metadata_comes_from_runtime_data():
    chunks = [
        Chunk("c1", "doc-a", "a"),
        Chunk("c2", "doc-a", "b"),
        Chunk("c3", "doc-b", "c"),
    ]
    report = {"n": 7, "overall_recall": 0.8}

    result = build_result(
        chunks=chunks,
        report=report,
        load_ms=12.0,
        eval_ms=34.0,
        run_at="2026-01-01T00:00:00+00:00",
    )

    assert result["cases"] == 7
    assert result["documents"] == 2
    assert result["chunks"] == 3


def test_benchmark_metadata_comes_from_runtime_chunks():
    chunks = [Chunk("c1", "doc-a", "a"), Chunk("c2", "doc-b", "b")]

    result = build_benchmark_result(chunks, cold=[10.0, 20.0], warm=[1.0, 2.0], run_at="now")

    assert result["documents"] == 2
    assert result["chunks"] == 2
