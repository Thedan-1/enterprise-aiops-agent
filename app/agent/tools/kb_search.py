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
        # Reranker分数低于阈值的证据被丢弃：Retrieval本身总会返回topK(哪怕全部不相关)，
        # 真正决定"这算不算相关证据"是这一层的职责，不是Pipeline的职责——这是Abstention
        # 真正生效的关键点，缺了这一步Recall会显得很高但其实是在拿不相关内容硬凑答案。
        # 见 docs/architecture.md ADR-005 和 docs/project_management.md 幻觉排查树。
        relevant_evidence = [e for e in output.evidence if e.score >= settings.reranker_min_score]

        if not relevant_evidence:
            return ToolResult(success=True, summary="知识库未检索到相关文档", evidence=[], debug=output.debug.as_dict())
        summary = f"检索到{len(relevant_evidence)}条相关证据，来源：" + "、".join(
            sorted({e.source for e in relevant_evidence})
        )
        return ToolResult(success=True, summary=summary, evidence=relevant_evidence, debug=output.debug.as_dict())
