"""可插拔 LLM Client。

默认 Provider = mock：确定性规则引擎，不调用任何外部API。用于验证 Agent Loop
状态机、Stop Condition、Tool 调用契约、Evidence 使用逻辑的正确性——
但不具备真实语义推理能力，不能代表生产环境下的诊断质量。

方法按"任务"划分（classify_intent / plan_next_action / generate_answer），
而不是暴露一个裸的 chat(prompt)->str，这样 Mock 实现可以针对每个任务写清晰规则，
真实 Provider 实现内部自己组 prompt + 解析结构化输出，对上层 Agent Loop 完全透明。
"""
import json
import re
from abc import ABC, abstractmethod

from app.agent.state import ObservationRecord, PlannerDecision
from app.core.config import settings
from app.core.types import Evidence, ToolSpec

DIAGNOSIS_KEYWORDS = [
    "502", "503", "500", "504", "错误", "异常", "故障", "慢", "超时", "timeout",
    "cpu", "内存", "memory", "qps", "崩溃", "宕机", "报错", "失败", "down",
]


class LLMClient(ABC):
    @abstractmethod
    def classify_intent(self, query: str) -> str: ...

    @abstractmethod
    def plan_next_action(
        self, query: str, intent: str, observations: list[ObservationRecord], available_tools: list[ToolSpec]
    ) -> PlannerDecision: ...

    @abstractmethod
    def generate_answer(self, query: str, observations: list[ObservationRecord]) -> str: ...


def _extract_service(query: str) -> str | None:
    m = re.search(r"([a-zA-Z\-]+(?:service|服务))", query, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"([一-龥]+服务)", query)
    return m.group(1) if m else None


class MockLLMClient(LLMClient):
    """规则引擎：iteration 0 先查知识库；诊断类任务再依次查 metrics/log；
    信息足够或工具都试过一遍后停止。"""

    def classify_intent(self, query: str) -> str:
        q = query.lower()
        return "diagnosis" if any(k in q for k in DIAGNOSIS_KEYWORDS) else "knowledge_qa"

    def plan_next_action(
        self, query: str, intent: str, observations: list[ObservationRecord], available_tools: list[ToolSpec]
    ) -> PlannerDecision:
        called = {o.tool_name for o in observations}
        tool_names = {t.name for t in available_tools}

        if "knowledge_search" not in called and "knowledge_search" in tool_names:
            return PlannerDecision(
                reasoning="先检索知识库,获取该问题相关的背景资料/已知案例",
                tool_name="knowledge_search",
                tool_input={"query": query},
                sufficient=False,
            )

        if intent == "diagnosis":
            service = _extract_service(query)
            if "service_metrics" not in called and "service_metrics" in tool_names and service:
                return PlannerDecision(
                    reasoning=f"诊断类问题,需要查看{service}当前实时指标是否异常",
                    tool_name="service_metrics",
                    tool_input={"service": service},
                    sufficient=False,
                )
            metrics_obs = next((o for o in observations if o.tool_name == "service_metrics"), None)
            metrics_abnormal = bool(metrics_obs and metrics_obs.result.success and "异常" in metrics_obs.result.summary)
            if metrics_abnormal and "log_query" not in called and "log_query" in tool_names and service:
                return PlannerDecision(
                    reasoning="指标显示异常,进一步查看错误日志定位具体原因",
                    tool_name="log_query",
                    tool_input={"service": service, "time_range": "last_10_minutes", "level": "ERROR"},
                    sufficient=False,
                )

        return PlannerDecision(reasoning="已收集足够证据,可以给出结论", tool_name=None, tool_input=None, sufficient=True)

    def generate_answer(self, query: str, observations: list[ObservationRecord]) -> str:
        all_evidence: list[Evidence] = []
        notes = []
        for obs in observations:
            if obs.result.success:
                all_evidence.extend(obs.result.evidence)
                notes.append(f"[{obs.tool_name}] {obs.result.summary}")
            else:
                notes.append(f"[{obs.tool_name}] 调用失败: {obs.result.error}")

        if not all_evidence and not any(o.result.success for o in observations):
            return (
                "当前知识库和工具数据不足以支持确定结论。\n"
                "已确认信息：无\n"
                f"未确认信息：'{query}' 相关的直接证据未找到\n"
                "建议下一步：请提供更具体的服务名/错误码，或人工排查。"
            )

        lines = ["诊断结论（基于以下证据综合得出，MockLLM生成，仅验证流程）：", ""]
        lines.extend(notes)
        lines.append("")
        if all_evidence:
            lines.append("引用来源：")
            for ev in all_evidence[:5]:
                lines.append(f"  - [{ev.source}] {ev.content[:80]}...")
        else:
            lines.append("注意：未检索到知识库证据，以上结论仅基于实时指标/日志观察，置信度较低。")
        return "\n".join(lines)


class AnthropicLLMClient(LLMClient):
    def __init__(self):
        from anthropic import Anthropic  # lazy import

        if not settings.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic 但未配置 ANTHROPIC_API_KEY")
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.llm_model

    def _call(self, system: str, user: str) -> str:
        resp = self.client.messages.create(
            model=self.model, max_tokens=1024, system=system, messages=[{"role": "user", "content": user}]
        )
        return resp.content[0].text

    def classify_intent(self, query: str) -> str:
        out = self._call(
            "只输出一个词：knowledge_qa 或 diagnosis。diagnosis表示需要实时指标/日志才能回答的故障诊断问题。",
            query,
        )
        return "diagnosis" if "diagnosis" in out.lower() else "knowledge_qa"

    def plan_next_action(
        self, query: str, intent: str, observations: list[ObservationRecord], available_tools: list[ToolSpec]
    ) -> PlannerDecision:
        tools_desc = "\n".join(f"- {t.name}: {t.description}" for t in available_tools)
        obs_desc = "\n".join(f"[{o.tool_name}] {o.result.summary}" for o in observations) or "(无)"
        prompt = (
            f"用户问题: {query}\n意图: {intent}\n可用工具:\n{tools_desc}\n\n已获得的观察:\n{obs_desc}\n\n"
            '严格输出JSON，不要多余文本: {"reasoning": "...", "tool_name": "xxx或null",'
            ' "tool_input": {}, "sufficient": true/false}'
        )
        out = self._call("你是运维诊断Agent的Planner，只输出JSON。", prompt)
        try:
            data = json.loads(out.strip().strip("`"))
            return PlannerDecision(
                reasoning=data.get("reasoning", ""),
                tool_name=data.get("tool_name"),
                tool_input=data.get("tool_input") or {},
                sufficient=bool(data.get("sufficient", False)),
            )
        except (json.JSONDecodeError, KeyError):
            return PlannerDecision(reasoning="解析失败,降级为停止", tool_name=None, tool_input=None, sufficient=True)

    def generate_answer(self, query: str, observations: list[ObservationRecord]) -> str:
        obs_desc = "\n\n".join(
            f"[{o.tool_name}]\n{o.result.summary}\nEvidence: "
            + "; ".join(f"({e.source}) {e.content}" for e in o.result.evidence)
            for o in observations
            if o.result.success
        )
        system = (
            "你是企业运维诊断助手。只能基于下面提供的证据回答，不能编造。"
            "如果证据不足以支持确定结论，必须明确说明'当前证据不足'，列出已确认/未确认信息,不要猜测。"
            "回答需包含：诊断结论、排查步骤、引用来源。"
        )
        return self._call(system, f"用户问题: {query}\n\n可用证据:\n{obs_desc or '(无证据)'}")


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient()
    return MockLLMClient()
