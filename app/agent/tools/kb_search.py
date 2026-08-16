from app.core.config import settings
from app.core.types import ToolResult
from app.rag.pipeline import RetrievalPipeline
from app.agent.tools.base import Tool


class KnowledgeSearchTool(Tool):
    name = "knowledge_search"
    description = "检索企业技术文档、故障案例、运维SOP，返回带引用来源的相关片段"
    input_schema = {"query": "str", "top_k": "int(optional)"}

    def __init__(self, pipeline: RetrievalPipeline, doc_titles: dict[str, str]):
        self.pipeline = pipeline
        self.doc_titles = doc_titles

    def _call(self, query: str, top_k: int | None = None) -> ToolResult:
        output = self.pipeline.retrieve(
            query,
            top_k_candidate=settings.retriever_top_k_candidate,
            top_k_final=top_k or settings.retriever_top_k_final,
            doc_titles=self.doc_titles,
        )
        if not output.evidence:
            return ToolResult(success=True, summary="知识库未检索到相关文档", evidence=[], debug=output.debug.as_dict())
        summary = f"检索到{len(output.evidence)}条相关证据，来源：" + "、".join(
            sorted({e.source for e in output.evidence})
        )
        return ToolResult(success=True, summary=summary, evidence=output.evidence, debug=output.debug.as_dict())
