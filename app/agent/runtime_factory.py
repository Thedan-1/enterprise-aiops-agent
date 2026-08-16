"""组装 AgentRuntime 所需的全部依赖：Embedder/Reranker/RetrievalPipeline/Tools/LLMClient。

被 app/main.py（服务启动）和 eval/run_eval.py（离线评测）共用，
保证"线上跑的Pipeline"和"评测用的Pipeline"是同一套代码，不会出现
"评测环境和生产环境实现不一致"这种常见的评测失真来源。
"""
from sqlalchemy.orm import Session

from app.agent.loop import AgentRuntime
from app.agent.tools.kb_search import KnowledgeSearchTool
from app.agent.tools.log_query import LogQueryTool
from app.agent.tools.service_metrics import ServiceMetricsTool
from app.core.config import settings
from app.core.embedder import get_embedder
from app.core.llm_client import get_llm_client
from app.core.types import Chunk
from app.db.models import Document, DocumentChunk
from app.rag.pipeline import RetrievalPipeline
from app.rag.reranker import get_reranker
from app.rag.retriever.dense import DenseRetriever
from app.rag.retriever.sparse import SparseRetriever


def load_chunks_and_titles(session: Session) -> tuple[list[Chunk], dict[str, str]]:
    rows = session.query(DocumentChunk).all()
    chunks = [
        Chunk(id=str(r.id), document_id=str(r.document_id), content=r.content, metadata=r.chunk_metadata or {})
        for r in rows
    ]
    doc_rows = session.query(Document).all()
    doc_titles = {str(d.id): d.title for d in doc_rows}
    return chunks, doc_titles


def build_retrieval_pipeline(session: Session) -> RetrievalPipeline:
    chunks, _ = load_chunks_and_titles(session)
    embedder = get_embedder()
    return RetrievalPipeline(DenseRetriever(session, embedder), SparseRetriever(chunks), get_reranker())


def build_agent_runtime(session: Session) -> AgentRuntime:
    chunks, doc_titles = load_chunks_and_titles(session)
    embedder = get_embedder()
    pipeline = RetrievalPipeline(DenseRetriever(session, embedder), SparseRetriever(chunks), get_reranker())

    tools = [
        KnowledgeSearchTool(pipeline, doc_titles),
        LogQueryTool(),
        ServiceMetricsTool(),
    ]
    return AgentRuntime(
        llm_client=get_llm_client(),
        tools=tools,
        max_iterations=settings.agent_max_iterations,
        timeout_s=settings.agent_timeout_s,
    )
