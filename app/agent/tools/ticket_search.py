from app.agent.tools.base import Tool
from app.agent.tools.service_names import canonical_service_name
from app.core.types import ToolResult
from data.mock.tickets import search_tickets


class TicketSearchTool(Tool):
    name = "ticket_search"
    description = "查询历史故障工单及其解决方案，可按服务名和/或关键词检索"
    input_schema = {"service": "str(optional)", "query": "str(optional)"}

    def _call(self, service: str = "", query: str = "") -> ToolResult:
        canonical_service = canonical_service_name(service) if service else ""
        tickets = search_tickets(query=query, service=canonical_service)
        if not tickets:
            return ToolResult(success=True, summary="未找到相关历史工单", debug={"tickets": []})
        summary = f"找到{len(tickets)}条相关历史工单: " + "; ".join(
            f"[{t['id']}] {t['title']}({t['status']})" for t in tickets[:3]
        )
        return ToolResult(success=True, summary=summary, debug={"tickets": tickets})
