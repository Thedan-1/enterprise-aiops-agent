from app.agent.tools.base import Tool
from app.agent.tools.service_metrics import _is_self_query
from app.agent.tools.service_names import KNOWN_SERVICES, TenantScopedService, canonical_service_name
from app.core.types import ToolResult
from data.mock.logs import get_logs
from data.real.self_logs import get_self_logs


class LogQueryTool(TenantScopedService, Tool):
    name = "log_query"
    description = (
        "查询指定服务在时间范围内的日志（默认ERROR级别）。"
        "服务名传'本机'/'self'/'这个系统'会查询这个Agent系统自己的真实运行日志(非mock)。"
    )
    input_schema = {"service": "str", "time_range": "str(optional)", "level": "str(optional)"}

    def _call(self, service: str, time_range: str = "last_10_minutes", level: str = "ERROR") -> ToolResult:
        if _is_self_query(service):
            self.scoped_service_name(service, self_query=True)
            lines = get_self_logs(level=level, limit=20)
            summary = (
                f"AIOps Agent自身运行日志: 最近{len(lines)}条{level}级别记录"
                if lines
                else f"AIOps Agent自身运行日志: 暂无{level}级别记录"
            )
            return ToolResult(success=True, summary=summary, debug={"raw_lines": lines})

        canonical_service = self.scoped_service_name(service)
        if canonical_service not in KNOWN_SERVICES:
            return ToolResult(
                success=False,
                summary="",
                error=f"未识别服务 '{service}'，无法确认是否存在错误日志",
            )
        lines = get_logs(service=canonical_service, time_range=time_range, level=level)
        has_errors = any("ERROR" in l for l in lines) if level.upper() == "ERROR" else bool(lines)
        summary = (
            f"{canonical_service} 在 {time_range} 内发现 {len(lines)} 条{level}日志: " + " | ".join(lines[:3])
            if has_errors
            else f"{canonical_service} 在 {time_range} 内无{level}级别日志"
        )
        return ToolResult(success=True, summary=summary, debug={"raw_lines": lines})
