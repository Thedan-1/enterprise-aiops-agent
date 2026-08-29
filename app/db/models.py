import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _uuid_col():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = _uuid_col()
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_col()
    external_subject: Mapped[str] = mapped_column(String, unique=True, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    role: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id: Mapped[uuid.UUID] = _uuid_col()
    name: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)
    tenant_slug: Mapped[str] = mapped_column(String, default="alpha", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _uuid_col()
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=True)
    title: Mapped[str] = mapped_column(String)
    tenant_slug: Mapped[str] = mapped_column(String, default="alpha", index=True)
    raw_content: Mapped[str] = mapped_column(Text)
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[uuid.UUID] = _uuid_col()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    tenant_slug: Mapped[str] = mapped_column(String, default="alpha", index=True)
    embedding = mapped_column(Vector(settings.embedder_dim), nullable=True)
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    embedding_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[str] = mapped_column(String, default="anonymous")
    tenant_slug: Mapped[str] = mapped_column(String, default="alpha", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _uuid_col()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = _uuid_col()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    request_id: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[str] = mapped_column(String, default="anonymous", index=True)
    tenant_slug: Mapped[str] = mapped_column(String, default="alpha", index=True)
    query: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String, default="unknown")
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    stop_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    total_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ToolCall(Base):
    __tablename__ = "tool_calls"
    id: Mapped[uuid.UUID] = _uuid_col()
    agent_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id"))
    iteration: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String)
    tenant_slug: Mapped[str] = mapped_column(String, default="alpha", index=True)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    id: Mapped[uuid.UUID] = _uuid_col()
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=True)
    tool_call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tool_calls.id"), nullable=True)
    query: Mapped[str] = mapped_column(Text)
    tenant_slug: Mapped[str] = mapped_column(String, default="alpha", index=True)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    bm25_candidates: Mapped[list] = mapped_column(JSON, default=list)
    dense_candidates: Mapped[list] = mapped_column(JSON, default=list)
    fusion_candidates: Mapped[list] = mapped_column(JSON, default=list)
    rerank_candidates: Mapped[list] = mapped_column(JSON, default=list)
    final_context: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    latency_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    id: Mapped[uuid.UUID] = _uuid_col()
    external_id: Mapped[str] = mapped_column(String, unique=True)
    question: Mapped[str] = mapped_column(Text)
    ground_truth_chunk_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    expected_answer_contains: Mapped[list] = mapped_column(ARRAY(String), default=list)
    category: Mapped[str] = mapped_column(String)
    difficulty: Mapped[str] = mapped_column(String, default="medium")
    requires_tool: Mapped[list] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    id: Mapped[uuid.UUID] = _uuid_col()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evaluation_cases.id"))
    eval_run_id: Mapped[str] = mapped_column(String)
    recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    mrr: Mapped[float | None] = mapped_column(Float, nullable=True)
    tool_selection_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    task_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = _uuid_col()
    tenant_slug: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    outcome: Mapped[str] = mapped_column(String)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
