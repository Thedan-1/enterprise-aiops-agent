from app.agent.tools.base import Tool
from app.core.types import ToolResult
from data.mock.logs import get_logs


class LogQueryTool(Tool):
    name = "log_query"
    description = "查询指定服务在时间范围内的日志（默认ERROR级别）"
    input_schema = {"service": "str", "time_range": "str(optional)", "level": "str(optional)"}

    def _call(self, service: str, time_range: str = "last_10_minutes", level: str = "ERROR") -> ToolResult:
        lines = get_logs(service=service, time_range=time_range, level=level)
        has_errors = any("ERROR" in l for l in lines) if level.upper() == "ERROR" else bool(lines)
        summary = (
            f"{service} 在 {time_range} 内发现 {len(lines)} 条{level}日志: " + " | ".join(lines[:3])
            if has_errors
            else f"{service} 在 {time_range} 内无{level}级别日志"
        )
        return ToolResult(success=True, summary=summary, debug={"raw_lines": lines})
