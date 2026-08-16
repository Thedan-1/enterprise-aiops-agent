"""跨模块共享的轻量数据类型，避免 rag/agent/llm_client 之间循环依赖。"""
from dataclasses import dataclass, field


@dataclass
class Chunk:
    id: str
    document_id: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    rank: int = -1


@dataclass
class Evidence:
    chunk_id: str
    content: str
    source: str  # 文档标题，用于citation
    score: float


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolResult:
    success: bool
    summary: str  # 给LLM看的精简观察结果
    evidence: list[Evidence] = field(default_factory=list)
    debug: dict | None = None  # 只落库，不进LLM context
    error: str | None = None
    latency_ms: float = 0.0
