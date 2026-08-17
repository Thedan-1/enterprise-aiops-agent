"""离线端到端演示 + 真实实验数据（不依赖 Postgres）。

背景：本次沙箱环境 Docker Desktop 因宿主机未开启 Windows 的 "Virtual Machine
Platform" 功能而无法启动 WSL2（错误码 WSL_E_VIRTUAL_MACHINE_PLATFORM_REQUIRED），
需要管理员权限+重启才能修复，不属于自动化流程可以处理的范围。为了仍然拿到
真实（而非继续等待或编造）的Pipeline运行数字，这个脚本用
InMemoryDenseRetriever（见 app/rag/retriever/in_memory_dense.py）替代对
Postgres 的依赖，Chunking/BM25/Fusion/Reranker/Agent Loop 全部是生产同一套代码，
唯一被替换的是"向量排序在内存里做还是在数据库里做"这一层。

用法：
  python scripts/offline_demo.py
"""
import json
import statistics
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.loop import AgentRuntime  # noqa: E402
from app.agent.tools.kb_search import KnowledgeSearchTool  # noqa: E402
from app.agent.tools.log_query import LogQueryTool  # noqa: E402
from app.agent.tools.service_metrics import ServiceMetricsTool  # noqa: E402
from app.agent.tools.ticket_search import TicketSearchTool  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.embedder import get_embedder  # noqa: E402
from app.core.llm_client import get_llm_client  # noqa: E402
from app.core.types import Chunk  # noqa: E402
from app.rag.chunking import chunk_markdown  # noqa: E402
from app.rag.pipeline import RetrievalPipeline  # noqa: E402
from app.rag.reranker import NoOpReranker, get_reranker  # noqa: E402
from app.rag.retriever.hybrid import reciprocal_rank_fusion  # noqa: E402
from app.rag.retriever.in_memory_dense import InMemoryDenseRetriever  # noqa: E402
from app.rag.retriever.sparse import SparseRetriever  # noqa: E402
from eval.metrics import mrr, precision_at_k, recall_at_k  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CASES_PATH = Path(__file__).resolve().parent.parent / "eval" / "dataset" / "eval_cases.json"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "eval" / "results"


def load_and_chunk(chunk_size: int = 512, overlap: int = 50):
    chunks: list[Chunk] = []
    doc_titles: dict[str, str] = {}
    for path in sorted(RAW_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        title = raw.splitlines()[0].lstrip("# ").strip() if raw else path.stem
        doc_id = str(uuid.uuid4())
        doc_titles[doc_id] = title
        for rc in chunk_markdown(raw, chunk_size=chunk_size, overlap=overlap):
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()), document_id=doc_id, content=rc.content,
                    metadata={"slug": path.stem, "title": title, "section_title": rc.section_title},
                )
            )
    return chunks, doc_titles


def build_pipeline(chunks, embedder, reranker) -> RetrievalPipeline:
    embeddings = embedder.embed([c.content for c in chunks])
    dense = InMemoryDenseRetriever(chunks, embeddings, embedder)
    sparse = SparseRetriever(chunks)
    return RetrievalPipeline(dense, sparse, reranker)


def _avg(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r[key] is not None]
    return round(statistics.mean(vals), 4) if vals else None


def _summarize(rows: list[dict]) -> dict:
    by_cat = {}
    for cat in sorted({r["category"] for r in rows}):
        cat_rows = [r for r in rows if r["category"] == cat]
        entry = {"n": len(cat_rows), "recall": _avg(cat_rows, "recall"),
                  "precision": _avg(cat_rows, "precision"), "mrr": _avg(cat_rows, "mrr")}
        if cat == "not_in_kb":
            entry["empty_result_rate"] = round(sum(1 for r in cat_rows if r["retrieved_empty"]) / len(cat_rows), 4)
        by_cat[cat] = entry
    return {
        "n": len(rows), "overall_recall": _avg(rows, "recall"),
        "overall_precision": _avg(rows, "precision"), "overall_mrr": _avg(rows, "mrr"),
        "by_category": by_cat,
    }


def run_retrieval_eval(pipeline: RetrievalPipeline, chunks: list[Chunk], top_k_final: int | None = None) -> dict:
    id_to_slug = {c.id: c.metadata.get("slug", "unknown") for c in chunks}
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    rows = []
    for case in cases:
        output = pipeline.retrieve(
            case["question"], top_k_candidate=settings.retriever_top_k_candidate,
            top_k_final=top_k_final or settings.retriever_top_k_final,
        )
        retrieved_slugs = [id_to_slug.get(c["chunk_id"], "unknown") for c in output.debug.rerank_candidates]
        gt = case["ground_truth_doc_slugs"]
        rows.append({
            "id": case["id"], "category": case["category"],
            "recall": recall_at_k(retrieved_slugs, gt), "precision": precision_at_k(retrieved_slugs, gt),
            "mrr": mrr(retrieved_slugs, gt), "retrieved_empty": len(retrieved_slugs) == 0,
        })
    return _summarize(rows)


def experiment_chunk_size() -> dict:
    print("\n=== 实验1: Chunk Size 对比 (256/512/1024, overlap=50) ===")
    embedder = get_embedder()
    reranker = get_reranker()
    results = {}
    for size in (256, 512, 1024):
        chunks, _ = load_and_chunk(chunk_size=size, overlap=50)
        pipeline = build_pipeline(chunks, embedder, reranker)
        report = run_retrieval_eval(pipeline, chunks)
        results[str(size)] = {"n_chunks": len(chunks), "recall": report["overall_recall"],
                               "precision": report["overall_precision"], "mrr": report["overall_mrr"]}
        print(f"  chunk_size={size}: n_chunks={len(chunks)} recall={report['overall_recall']} "
              f"precision={report['overall_precision']} mrr={report['overall_mrr']}")
    return results


def experiment_retrieval_strategy() -> dict:
    print("\n=== 实验3: Dense-only / BM25-only / Hybrid 对比 (候选池直接评测,跳过Reranker以隔离变量) ===")
    chunks, _ = load_and_chunk(chunk_size=512, overlap=50)
    embedder = get_embedder()
    embeddings = embedder.embed([c.content for c in chunks])
    dense = InMemoryDenseRetriever(chunks, embeddings, embedder)
    sparse = SparseRetriever(chunks)
    id_to_slug = {c.id: c.metadata.get("slug", "unknown") for c in chunks}
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def hybrid_search(q, top_k):
        return reciprocal_rank_fusion([sparse.search(q, top_k), dense.search(q, top_k)], top_k=top_k)

    def eval_retriever(search_fn) -> dict:
        rows = []
        for case in cases:
            results = search_fn(case["question"], settings.retriever_top_k_candidate)
            retrieved_slugs = [id_to_slug.get(sc.chunk.id, "unknown") for sc in results]
            gt = case["ground_truth_doc_slugs"]
            rows.append({"category": case["category"], "recall": recall_at_k(retrieved_slugs, gt),
                         "precision": precision_at_k(retrieved_slugs, gt), "mrr": mrr(retrieved_slugs, gt),
                         "retrieved_empty": len(retrieved_slugs) == 0})
        return _summarize(rows)

    results = {"dense_only": eval_retriever(dense.search), "bm25_only": eval_retriever(sparse.search),
               "hybrid": eval_retriever(hybrid_search)}
    for name, r in results.items():
        print(f"  {name}: recall={r['overall_recall']} precision={r['overall_precision']} mrr={r['overall_mrr']}")
    return results


def experiment_reranker_on_off() -> dict:
    print("\n=== 实验4: Reranker 有无对比 (Fusion Top30 -> 直接截Top5 vs 精排后取Top5) ===")
    chunks, _ = load_and_chunk(chunk_size=512, overlap=50)
    embedder = get_embedder()
    pipeline_with = build_pipeline(chunks, embedder, get_reranker())
    pipeline_without = build_pipeline(chunks, embedder, NoOpReranker())

    with_r = run_retrieval_eval(pipeline_with, chunks)
    without_r = run_retrieval_eval(pipeline_without, chunks)
    print(f"  with_reranker:    recall={with_r['overall_recall']} precision={with_r['overall_precision']} mrr={with_r['overall_mrr']}")
    print(f"  without_reranker: recall={without_r['overall_recall']} precision={without_r['overall_precision']} mrr={without_r['overall_mrr']}")
    return {"with_reranker": with_r, "without_reranker": without_r}


def experiment_max_iterations() -> dict:
    print("\n=== 实验7: Max Iterations 对比 (3/5/8, timeout统一放宽到60s以隔离变量) ===")
    chunks, doc_titles = load_and_chunk(chunk_size=512, overlap=50)
    embedder = get_embedder()
    pipeline = build_pipeline(chunks, embedder, get_reranker())
    llm_client = get_llm_client()

    test_queries = [
        "order-service最近大量出现502，帮我分析可能原因并给出排查步骤",
        "inventory-service内存持续升高，响应变慢，怎么排查",
    ]
    results = {}
    for max_iter in (3, 5, 8):
        tools = [KnowledgeSearchTool(pipeline, doc_titles), LogQueryTool(), ServiceMetricsTool(), TicketSearchTool()]
        runtime = AgentRuntime(llm_client, tools, max_iterations=max_iter, timeout_s=60.0)
        runs = []
        for q in test_queries:
            r = runtime.run(q)
            runs.append({
                "query": q, "status": r.status, "confidence": r.confidence,
                "iterations": r.iterations, "stop_reason": r.stop_reason,
                "latency_ms": round(r.total_latency_ms, 1),
            })
        converged = sum(1 for run in runs if run["stop_reason"] == "planner_sufficient")
        results[str(max_iter)] = {"runs": runs, "converged_naturally": converged, "n": len(runs)}
        print(f"  max_iterations={max_iter}: converged_naturally={converged}/{len(runs)}")
        for run in runs:
            print(f"    - {run['query'][:24]}... -> status={run['status']} iterations={run['iterations']} "
                  f"stop_reason={run['stop_reason']} latency={run['latency_ms']}ms")
    return results


def run_agent_demo() -> list[dict]:
    print(f"\n=== Agent Loop Demo (LLM={settings.llm_provider}, 3个真实query) ===")
    chunks, doc_titles = load_and_chunk(chunk_size=512, overlap=50)
    embedder = get_embedder()
    pipeline = build_pipeline(chunks, embedder, get_reranker())
    tools = [KnowledgeSearchTool(pipeline, doc_titles), LogQueryTool(), ServiceMetricsTool(), TicketSearchTool()]
    runtime = AgentRuntime(get_llm_client(), tools, max_iterations=settings.agent_max_iterations,
                            timeout_s=settings.agent_timeout_s)

    demo_queries = [
        "order-service最近大量出现502，帮我分析可能原因并给出排查步骤",
        "什么是缓存穿透",
        "公司的年假申请流程是什么",
    ]
    transcripts = []
    for q in demo_queries:
        result = runtime.run(q)
        print(f"\n--- Query: {q} ---")
        print(f"intent={result.intent} status={result.status} confidence={result.confidence} "
              f"iterations={result.iterations} stop_reason={result.stop_reason}")
        for obs in result.observations:
            print(f"  [{obs.tool_name}] success={obs.result.success} summary={obs.result.summary[:120]}")
        print(f"Answer:\n{result.answer}")
        transcripts.append({
            "query": q, "intent": result.intent, "status": result.status, "confidence": result.confidence,
            "iterations": result.iterations, "stop_reason": result.stop_reason,
            "tool_calls": [{"tool": o.tool_name, "success": o.result.success, "summary": o.result.summary} for o in result.observations],
            "answer": result.answer,
        })
    return transcripts


if __name__ == "__main__":
    print(f"Provider: EMBEDDER={settings.embedder_provider} RERANKER={settings.reranker_provider} LLM={settings.llm_provider}")
    print("(默认Provider为占位实现,以下数字反映占位Embedder/Reranker/MockLLM的真实能力,不代表生产级模型效果)")

    chunks, doc_titles = load_and_chunk(chunk_size=512, overlap=50)
    embedder = get_embedder()
    reranker = get_reranker()
    pipeline = build_pipeline(chunks, embedder, reranker)
    n_docs = len(list(RAW_DIR.glob("*.md")))
    print(f"\n已加载 {n_docs} 篇文档, 切分为 {len(chunks)} 个chunk (chunk_size=512, overlap=50)")

    print("\n=== 基线 Retrieval 评测 (30条评测集, Hybrid+Rerank) ===")
    baseline = run_retrieval_eval(pipeline, chunks)
    print(json.dumps(baseline, ensure_ascii=False, indent=2))

    chunk_size_results = experiment_chunk_size()
    strategy_results = experiment_retrieval_strategy()
    reranker_results = experiment_reranker_on_off()
    agent_transcripts = run_agent_demo()
    max_iter_results = experiment_max_iterations() if settings.llm_provider != "mock" else None
    if max_iter_results is None:
        print("\n=== 实验7: Max Iterations 对比 跳过 (需要真实LLM,当前LLM_PROVIDER=mock没有意义) ===")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"offline_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(
        json.dumps(
            {
                "provider": {"embedder": settings.embedder_provider, "reranker": settings.reranker_provider, "llm": settings.llm_provider},
                "n_docs": n_docs, "n_chunks_baseline": len(chunks),
                "baseline_retrieval": baseline, "chunk_size_experiment": chunk_size_results,
                "retrieval_strategy_experiment": strategy_results, "reranker_on_off_experiment": reranker_results,
                "agent_demo": agent_transcripts, "max_iterations_experiment": max_iter_results,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n完整结果已写入: {out_path}")
