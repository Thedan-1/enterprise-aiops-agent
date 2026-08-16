import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.loop import AgentRuntime
from app.db.models import AgentRun, RetrievalLog, ToolCall
from app.db.session import get_session

router = APIRouter()


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    confidence: float
    status: str
    stop_reason: str
    iterations: int
    total_latency_ms: float


def get_agent_runtime(request: Request) -> AgentRuntime:
    return request.app.state.agent_runtime


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    runtime: AgentRuntime = Depends(get_agent_runtime),
    session: Session = Depends(get_session),
):
    request_id = str(uuid.uuid4())
    result = runtime.run(body.query, request_id=request_id)
    _persist_run(session, result)

    return ChatResponse(
        request_id=result.request_id,
        answer=result.answer,
        confidence=result.confidence,
        status=result.status,
        stop_reason=result.stop_reason,
        iterations=result.iterations,
        total_latency_ms=result.total_latency_ms,
    )


def _persist_run(session: Session, result) -> None:
    """落库 agent_runs/tool_calls/retrieval_logs，支撑事后排查（可观测性要求）。"""
    run_row = AgentRun(
        request_id=result.request_id,
        query=result.query,
        intent=result.intent,
        final_answer=result.answer,
        confidence=result.confidence,
        status=result.status,
        stop_reason=result.stop_reason,
        total_latency_ms=result.total_latency_ms,
    )
    session.add(run_row)
    session.flush()

    for obs in result.observations:
        tool_call_row = ToolCall(
            agent_run_id=run_row.id,
            iteration=obs.iteration,
            tool_name=obs.tool_name,
            input=obs.tool_input,
            output={"summary": obs.result.summary, "error": obs.result.error},
            latency_ms=obs.result.latency_ms,
            status="success" if obs.result.success else "error",
        )
        session.add(tool_call_row)
        session.flush()

        if obs.tool_name == "knowledge_search" and obs.result.debug:
            debug = obs.result.debug
            session.add(
                RetrievalLog(
                    agent_run_id=run_row.id,
                    tool_call_id=tool_call_row.id,
                    query=debug.get("query", result.query),
                    rewritten_query=debug.get("rewritten_query"),
                    bm25_candidates=debug.get("bm25_candidates", []),
                    dense_candidates=debug.get("dense_candidates", []),
                    fusion_candidates=debug.get("fusion_candidates", []),
                    rerank_candidates=debug.get("rerank_candidates", []),
                    final_context=[uuid.UUID(e.chunk_id) for e in obs.result.evidence],
                    latency_breakdown=debug.get("latency_breakdown", {}),
                )
            )
    session.commit()
