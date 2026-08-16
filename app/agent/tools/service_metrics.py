from app.agent.tools.base import Tool
from app.core.types import ToolResult
from data.mock.metrics import get_metrics


class ServiceMetricsTool(Tool):
    name = "service_metrics"
    description = "查询指定服务的实时指标：CPU/Memory/QPS/ErrorRate/P95延迟/状态"
    input_schema = {"service": "str"}

    def _call(self, service: str) -> ToolResult:
        m = get_metrics(service)
        if m["status"] == "unknown":
            return ToolResult(success=False, summary="", error=f"未找到服务 '{service}' 的指标数据")
        label = "异常" if m["status"] == "degraded" else "正常"
        summary = (
            f"{m['service']} 状态{label}: CPU {m['cpu_percent']}%, Memory {m['memory_percent']}%, "
            f"QPS {m['qps']}, ErrorRate {m['error_rate']*100:.1f}%, P95 {m['p95_latency_ms']}ms"
        )
        return ToolResult(success=True, summary=summary, debug=m)
