from app.agent.tools.base import Tool
from app.agent.tools.service_names import TenantScopedService, canonical_service_name
from app.core.types import ToolResult
from data.mock.metrics import get_metrics
from data.real.host_metrics import get_host_metrics

SELF_KEYWORDS = ("self", "本机", "宿主机", "这个系统", "这台机器", "当前系统", "aiops-agent", "aiops agent")


def _is_self_query(service: str) -> bool:
    s = service.strip().lower()
    return any(k in s for k in SELF_KEYWORDS)


class ServiceMetricsTool(TenantScopedService, Tool):
    name = "service_metrics"
    description = (
        "查询指定服务的实时指标：CPU/Memory/QPS/ErrorRate/P95延迟/状态。"
        "服务名传'本机'/'self'/'这个系统'会查询运行这个Agent系统本身的真实主机指标(非mock)。"
    )
    input_schema = {"service": "str"}

    def _call(self, service: str) -> ToolResult:
        if _is_self_query(service):
            self.scoped_service_name(service, self_query=True)
            m = get_host_metrics()
            label = "异常" if m["status"] == "degraded" else "正常"
            summary = (
                f"{m['service']} 状态{label}: CPU {m['cpu_percent']}%, Memory {m['memory_percent']}%, "
                f"Disk {m['disk_percent']}%, 进程数 {m['process_count']}"
            )
            return ToolResult(success=True, summary=summary, debug=m)

        canonical_service = self.scoped_service_name(service)
        m = get_metrics(canonical_service)
        if m["status"] == "unknown":
            return ToolResult(success=False, summary="", error=f"未找到服务 '{service}' 的指标数据")
        label = "异常" if m["status"] == "degraded" else "正常"
        summary = (
            f"{m['service']} 状态{label}: CPU {m['cpu_percent']}%, Memory {m['memory_percent']}%, "
            f"QPS {m['qps']}, ErrorRate {m['error_rate']*100:.1f}%, P95 {m['p95_latency_ms']}ms"
        )
        return ToolResult(success=True, summary=summary, debug=m)
