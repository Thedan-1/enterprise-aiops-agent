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

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.agent.loop import AgentRuntime
from app.agent.tools.kb_search import KnowledgeSearchTool
from app.agent.tools.log_query import LogQueryTool
from app.agent.tools.service_metrics import ServiceMetricsTool
from app.agent.tools.ticket_search import TicketSearchTool
from app.auth.service import AuthContext, AuthError, AuthService
from app.core.config import settings
from app.core.embedder import get_embedder
from app.core.llm_client import get_llm_client
from app.core.logging import setup_logging
from app.rag.reranker import get_reranker
from app.security.audit import AuditEvent, AuditStore
from app.security.guard import inspect_query
from app.security.policy import allowed_tools, can_read_audit
from app.security.rate_limit import SlidingWindowRateLimiter
from scripts.offline_demo import build_pipeline, load_and_chunk

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "offline_app.log"
AUDIT_FILE = Path(__file__).resolve().parent.parent / "logs" / "audit.jsonl"


def scope_chunks_for_tenant(chunks, tenant_id: str):
    """Return a separate corpus per tenant; never ask the LLM to filter tenant data."""
    if tenant_id == "alpha":
        return list(chunks)
    if tenant_id == "beta":
        beta_slugs = {"redis_common_issues", "http_status_codes_reference", "nginx_502_gateway_troubleshooting"}
        return [c for c in chunks if c.metadata.get("slug") in beta_slugs]
    return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(log_file=LOG_FILE)
    chunks, doc_titles = load_and_chunk(chunk_size=512, overlap=50)
    embedder = get_embedder()
    reranker = get_reranker()

    def runtime_for(tenant_chunks):
        pipeline = build_pipeline(tenant_chunks, embedder, reranker)
        tools = [KnowledgeSearchTool(pipeline, doc_titles), LogQueryTool(), ServiceMetricsTool(), TicketSearchTool()]
        return AgentRuntime(get_llm_client(), tools, settings.agent_max_iterations, settings.agent_timeout_s)

    app.state.agent_runtimes = {
        tenant: runtime_for(scope_chunks_for_tenant(chunks, tenant)) for tenant in ("alpha", "beta")
    }
    app.state.auth = AuthService()
    app.state.rate_limiter = SlidingWindowRateLimiter(limit=10, window_s=60)
    app.state.audit = AuditStore(AUDIT_FILE)
    app.state.n_chunks = len(chunks)
    app.state.n_docs = len({c.document_id for c in chunks})
    yield


app = FastAPI(title="OpsPilot (Offline Demo Mode)", lifespan=lifespan)


class ChatRequest(BaseModel):
    query: str


class LoginRequest(BaseModel):
    username: str
    password: str


def current_user(request: Request, authorization: str | None = Header(default=None)) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        return request.app.state.auth.verify(authorization.removeprefix("Bearer ").strip())
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/login")
def login(body: LoginRequest, request: Request):
    try:
        token = request.app.state.auth.login(body.username, body.password)
        context = request.app.state.auth.verify(token)
        request.app.state.audit.append(AuditEvent("login", "success", context.user_id, context.tenant_id))
        return {"access_token": token, "token_type": "bearer", "user": context.__dict__}
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


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


@app.get("/api/me")
def me(user: AuthContext = Depends(current_user)):
    return user.__dict__


@app.get("/api/audit")
def audit(request: Request, user: AuthContext = Depends(current_user)):
    if not can_read_audit(user):
        raise HTTPException(status_code=403, detail="仅审计员可查看审计记录")
    return {"events": request.app.state.audit.list_for_tenant(user.tenant_id)}


@app.post("/api/chat")
def chat(body: ChatRequest, request: Request, user: AuthContext = Depends(current_user)):
    guard = inspect_query(body.query)
    if not guard.allowed:
        request.app.state.audit.append(AuditEvent("chat", "blocked", user.user_id, user.tenant_id, detail=guard.reason))
        raise HTTPException(status_code=400, detail=guard.reason)
    if not request.app.state.rate_limiter.allow(f"{user.tenant_id}:{user.user_id}"):
        request.app.state.audit.append(AuditEvent("chat", "rate_limited", user.user_id, user.tenant_id))
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

    runtime: AgentRuntime = request.app.state.agent_runtimes[user.tenant_id]
    result = runtime.run(body.query, allowed_tool_names=allowed_tools(user))
    request.app.state.audit.append(
        AuditEvent("chat", result.status, user.user_id, user.tenant_id, result.request_id, result.stop_reason)
    )
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
