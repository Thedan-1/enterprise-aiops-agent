"""不依赖 Postgres 的 Web 入口。

复用 scripts/offline_demo.py 里已经跑通的内存版 Pipeline（Chunking→BM25+Dense
→Fusion→Reranker→Agent Loop 全部是和生产路径相同的代码，唯一区别是 Dense 检索
用 InMemoryDenseRetriever 而不是连 Postgres），让用户在 Docker/Postgres 环境
准备好之前，就能打开浏览器和真实 Agent 对话，而不是只能看代码和实验记录。

用法:
  uvicorn app.offline_app:app --reload --port 8001
  然后打开 http://127.0.0.1:8001

不做持久化（不写 agent_runs/tool_calls 这些表，因为没有数据库）——这是
Demo 模式和生产模式（app/main.py）的唯一功能性差异，Agent 本身的行为完全一致。
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.agent.loop import AgentRuntime
from app.agent.tools.kb_search import KnowledgeSearchTool
from app.agent.tools.log_query import LogQueryTool
from app.agent.tools.service_metrics import ServiceMetricsTool
from app.agent.tools.ticket_search import TicketSearchTool
from app.core.config import settings
from app.core.embedder import get_embedder
from app.core.llm_client import get_llm_client
from app.core.logging import setup_logging
from app.rag.reranker import get_reranker
from scripts.offline_demo import build_pipeline, load_and_chunk

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    chunks, doc_titles = load_and_chunk(chunk_size=512, overlap=50)
    pipeline = build_pipeline(chunks, get_embedder(), get_reranker())
    tools = [
        KnowledgeSearchTool(pipeline, doc_titles),
        LogQueryTool(),
        ServiceMetricsTool(),
        TicketSearchTool(),
    ]
    app.state.agent_runtime = AgentRuntime(
        llm_client=get_llm_client(),
        tools=tools,
        max_iterations=settings.agent_max_iterations,
        timeout_s=settings.agent_timeout_s,
    )
    app.state.n_chunks = len(chunks)
    app.state.n_docs = len({c.document_id for c in chunks})
    yield


app = FastAPI(title="AIOps Agent (Offline Demo Mode)", lifespan=lifespan)


class ChatRequest(BaseModel):
    query: str


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health(request: Request):
    return {
        "status": "ok",
        "mode": "offline_in_memory",
        "n_docs": request.app.state.n_docs,
        "n_chunks": request.app.state.n_chunks,
        "provider": {
            "embedder": settings.embedder_provider,
            "reranker": settings.reranker_provider,
            "llm": settings.llm_provider,
        },
    }


@app.post("/api/chat")
def chat(body: ChatRequest, request: Request):
    runtime: AgentRuntime = request.app.state.agent_runtime
    result = runtime.run(body.query)
    return {
        "request_id": result.request_id,
        "query": result.query,
        "intent": result.intent,
        "answer": result.answer,
        "status": result.status,
        "confidence": result.confidence,
        "iterations": result.iterations,
        "stop_reason": result.stop_reason,
        "total_latency_ms": round(result.total_latency_ms, 1),
        "tool_calls": [
            {
                "tool": o.tool_name,
                "input": o.tool_input,
                "success": o.result.success,
                "summary": o.result.summary,
                "error": o.result.error,
                "latency_ms": round(o.result.latency_ms, 1),
                "evidence": [
                    {"source": e.source, "content": e.content, "score": round(e.score, 3)}
                    for e in o.result.evidence
                ],
            }
            for o in result.observations
        ],
    }
