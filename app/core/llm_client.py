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

    @abstractmethod
    def is_evidence_relevant(self, query: str, evidence_texts: list[str]) -> bool:
        """Evidence Validation（对应需求里的Context Relevance）：判断检索到的证据
        是否真的能支撑回答这个问题，而不是"分数刚好压线过了阈值但主题不相关"。
        这是一个窄范围的相关性判断任务，不是让LLM自评"我有多确信"（那个不可靠，
        见validator.py顶部说明），是两回事：相关性判断可以对照具体证据文本核实，
        置信度自评没有对照物。"""
        ...


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
            if metrics_abnormal and "ticket_search" not in called and "ticket_search" in tool_names and service:
                return PlannerDecision(
                    reasoning="确认存在异常,查一下历史上这个服务是否有过类似的已解决工单,参考修复方案",
                    tool_name="ticket_search",
                    tool_input={"service": service},
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

    def is_evidence_relevant(self, query: str, evidence_texts: list[str]) -> bool:
        """Mock没有语义理解能力，退化成词面重合度启发式：query的token至少有
        一部分出现在证据里，才算相关。这是故意粗糙的近似，真实Provider应该
        用LLM做语义判断，见PromptedLLMClient的实现。"""
        from app.rag.retriever.sparse import tokenize  # 延迟导入,避免core->rag的静态耦合面扩大

        query_tokens = set(tokenize(query))
        if not query_tokens or not evidence_texts:
            return False
        evidence_tokens = set(tokenize(" ".join(evidence_texts)))
        overlap_ratio = len(query_tokens & evidence_tokens) / len(query_tokens)
        return overlap_ratio >= 0.2


class PromptedLLMClient(LLMClient):
    """真实LLM Provider的共享逻辑：Provider之间只有'怎么发HTTP请求'不同
    （_call方法），classify_intent/plan_next_action/generate_answer 的
    prompt设计和JSON解析逻辑是一样的，抽到基类避免重复。"""

    def _call(self, system: str, user: str) -> str:
        raise NotImplementedError

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
        planner_system = (
            "你是运维诊断Agent的Planner，只输出JSON。规则：(1) 只要还没有调用过knowledge_search，"
            "就不能判断sufficient=true——哪怕你自己知道这个概念/术语的通用定义，企业内部的具体实现、"
            "SOP、历史故障案例也可能和通用定义不同，必须先查证企业知识库再回答，这是避免幻觉的强制要求；"
            "(2) 诊断类问题在拿到knowledge_search证据之后，如果还有明确的异常信号(错误日志/异常指标)"
            "没有查证，应继续调用log_query/service_metrics；一旦已经有能支撑结论的证据链，就应该"
            "sufficient=true，不要为了'更完整'无限调用工具；(3) 同一个工具不要连续对同一个service重复调用。"
        )
        out = self._call(planner_system, prompt)
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

    def is_evidence_relevant(self, query: str, evidence_texts: list[str]) -> bool:
        if not evidence_texts:
            return False
        evidence_block = "\n---\n".join(t[:300] for t in evidence_texts[:5])
        system = (
            "你是严格的证据相关性审核员。只判断:下面这些证据内容,是否真的能支撑回答用户的问题"
            "(哪怕只能支撑部分回答也算相关;如果证据讨论的是完全不同的主题,即使有零星字面重合也判不相关)。"
            "只输出一个词: yes 或 no,不要输出其他任何内容。"
        )
        out = self._call(system, f"用户问题: {query}\n\n证据:\n{evidence_block}")
        return out.strip().lower().startswith("y")


class AnthropicLLMClient(PromptedLLMClient):
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


class DeepSeekLLMClient(PromptedLLMClient):
    """DeepSeek 走 OpenAI 兼容的 REST 接口，用项目已有的 httpx 直接调，
    不额外引入 openai SDK 依赖。"""

    def __init__(self):
        import httpx

        if not settings.deepseek_api_key:
            raise RuntimeError("LLM_PROVIDER=deepseek 但未配置 DEEPSEEK_API_KEY")
        self._httpx = httpx
        self.base_url = settings.deepseek_base_url
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model

    def _call(self, system: str, user: str) -> str:
        resp = self._httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "stream": False,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient()
    if settings.llm_provider == "deepseek":
        return DeepSeekLLMClient()
    return MockLLMClient()
