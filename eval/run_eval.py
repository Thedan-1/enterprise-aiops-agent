"""离线评测入口。

用法：
  python eval/run_eval.py                  # 只跑Retrieval评测（Recall/Precision/MRR）
  python eval/run_eval.py --with-agent      # 额外跑一遍完整Agent Loop，统计Abstention/Answered情况

不伪造任何数字——所有输出都是本次真实运行的结果，跑不出来就是跑不出来，
报告里会如实写运行时用的Provider（mock_hash/mock LLM 还是真实API）。
"""
import argparse
import json
import statistics
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.runtime_factory import build_agent_runtime, build_retrieval_pipeline  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.models import DocumentChunk  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from eval.metrics import mrr, precision_at_k, recall_at_k  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "dataset" / "eval_cases.json"


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def chunk_id_to_slug_map(session) -> dict[str, str]:
    rows = session.query(DocumentChunk).all()
    return {str(r.id): (r.chunk_metadata or {}).get("slug", "unknown") for r in rows}


def run_retrieval_eval(top_k_final: int | None = None) -> dict:
    session = SessionLocal()
    try:
        pipeline = build_retrieval_pipeline(session)
        id_to_slug = chunk_id_to_slug_map(session)
        cases = load_cases()

        rows = []
        for case in cases:
            output = pipeline.retrieve(
                case["question"],
                top_k_candidate=settings.retriever_top_k_candidate,
                top_k_final=top_k_final or settings.retriever_top_k_final,
            )
            retrieved_slugs = [id_to_slug.get(c["chunk_id"], "unknown") for c in output.debug.rerank_candidates]
            gt = case["ground_truth_doc_slugs"]

            r = recall_at_k(retrieved_slugs, gt)
            p = precision_at_k(retrieved_slugs, gt)
            m = mrr(retrieved_slugs, gt)
            rows.append(
                {
                    "id": case["id"], "category": case["category"], "recall": r, "precision": p, "mrr": m,
                    "retrieved_slugs": retrieved_slugs, "ground_truth": gt,
                    "abstained_correctly": (not gt) and (not retrieved_slugs),
                }
            )
        return summarize(rows)
    finally:
        session.close()


def summarize(rows: list[dict]) -> dict:
    def avg(key, filt=None):
        vals = [r[key] for r in rows if r[key] is not None and (filt is None or filt(r))]
        return round(statistics.mean(vals), 4) if vals else None

    by_category = {}
    for cat in {r["category"] for r in rows}:
        cat_rows = [r for r in rows if r["category"] == cat]
        by_category[cat] = {
            "n": len(cat_rows),
            "recall": avg("recall", lambda r: r["category"] == cat),
            "precision": avg("precision", lambda r: r["category"] == cat),
            "mrr": avg("mrr", lambda r: r["category"] == cat),
        }

    not_in_kb_rows = [r for r in rows if r["category"] == "not_in_kb"]
    abstention_rate = (
        round(sum(1 for r in not_in_kb_rows if not r["retrieved_slugs"]) / len(not_in_kb_rows), 4)
        if not_in_kb_rows
        else None
    )

    return {
        "n_cases": len(rows),
        "overall_recall": avg("recall"),
        "overall_precision": avg("precision"),
        "overall_mrr": avg("mrr"),
        "by_category": by_category,
        "not_in_kb_empty_result_rate": abstention_rate,
        "detail": rows,
    }


def run_agent_eval(sample_size: int = 10) -> dict:
    session = SessionLocal()
    try:
        runtime = build_agent_runtime(session)
        cases = load_cases()[:sample_size]
        results = []
        for case in cases:
            r = runtime.run(case["question"], request_id=str(uuid.uuid4()))
            results.append(
                {
                    "id": case["id"], "category": case["category"], "status": r.status,
                    "confidence": r.confidence, "iterations": r.iterations, "stop_reason": r.stop_reason,
                }
            )
        not_in_kb = [r for r in results if r["category"] == "not_in_kb"]
        correct_abstain = sum(1 for r in not_in_kb if r["status"] == "abstained")
        return {
            "n_sampled": len(results),
            "not_in_kb_abstain_accuracy": (correct_abstain / len(not_in_kb)) if not_in_kb else None,
            "avg_iterations": round(statistics.mean(r["iterations"] for r in results), 2),
            "detail": results,
        }
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-agent", action="store_true")
    parser.add_argument("--agent-sample", type=int, default=10)
    args = parser.parse_args()

    print(f"Provider: EMBEDDER={settings.embedder_provider}, RERANKER={settings.reranker_provider}, LLM={settings.llm_provider}")
    print("\n=== Retrieval Evaluation ===")
    retrieval_report = run_retrieval_eval()
    print(json.dumps({k: v for k, v in retrieval_report.items() if k != "detail"}, ensure_ascii=False, indent=2))

    if args.with_agent:
        print(f"\n=== Agent Evaluation (sample={args.agent_sample}) ===")
        agent_report = run_agent_eval(sample_size=args.agent_sample)
        print(json.dumps({k: v for k, v in agent_report.items() if k != "detail"}, ensure_ascii=False, indent=2))
