"""Agent Runtime：手写 Agent Loop（不用LangGraph，见 architecture.md ADR-002）。

while not stop:
    decide_next_action()      -> Planner (LLM，结构化输出)
    if tool_needed: call_tool() -> observe_result()
    else: generate_final_answer()

Stop Condition 是纯函数（AgentState.should_stop），不依赖LLM自由文本解析，
这样这个循环本身可以脱离真实LLM单独写单测（见 tests/unit/test_agent_state.py）。
"""
import logging
import time
import uuid
from dataclasses import dataclass, field

from app.agent.state import AgentState, ObservationRecord
from app.agent.tools.base import Tool
from app.agent.validator import validate
from app.core.llm_client import LLMClient

logger = logging.getLogger("agent.loop")


@dataclass
class AgentRunResult:
    request_id: str
    query: str
    intent: str
    answer: str
    confidence: float
    status: str  # answered / abstained / error
    stop_reason: str
    iterations: int
    observations: list[ObservationRecord] = field(default_factory=list)
    total_latency_ms: float = 0.0


class AgentRuntime:
    def __init__(self, llm_client: LLMClient, tools: list[Tool], max_iterations: int = 5, timeout_s: float = 30.0):
        self.llm_client = llm_client
        self.tools_by_name = {t.name: t for t in tools}
        self.max_iterations = max_iterations
        self.timeout_s = timeout_s

    def run(
        self,
        query: str,
        request_id: str | None = None,
        allowed_tool_names: set[str] | None = None,
    ) -> AgentRunResult:
        request_id = request_id or str(uuid.uuid4())
        state = AgentState(
            request_id=request_id, query=query, max_iterations=self.max_iterations, timeout_s=self.timeout_s
        )
        state.intent = self.llm_client.classify_intent(query)
        logger.info("intent classified", extra={"request_id": request_id, "stage": "intent"})

        allowed = allowed_tool_names if allowed_tool_names is not None else set(self.tools_by_name)
        tool_specs = [t.spec() for name, t in self.tools_by_name.items() if name in allowed]

        while True:
            decision = self.llm_client.plan_next_action(query, state.intent, state.observations, tool_specs)
            stop, reason = state.should_stop(decision)
            if stop:
                state.stop_reason = reason
                break

            if decision.tool_name not in allowed:
                state.stop_reason = f"forbidden_tool:{decision.tool_name}"
                break

            tool = self.tools_by_name.get(decision.tool_name)
            if tool is None:
                state.stop_reason = f"unknown_tool:{decision.tool_name}"
                break

            result = tool.call(**(decision.tool_input or {}))
            state.record_call(state.iteration, decision.tool_name, decision.tool_input or {}, result)
            logger.info(
                "tool call",
                extra={
                    "request_id": request_id,
                    "tool_name": decision.tool_name,
                    "latency_ms": result.latency_ms,
                    "stage": "tool_call",
                },
            )
            state.iteration += 1

        answer = self.llm_client.generate_answer(query, state.observations)
        validation = validate(query, state.observations, self.llm_client)
        status = "answered" if validation.grounded else "abstained"

        return AgentRunResult(
            request_id=request_id,
            query=query,
            intent=state.intent,
            answer=answer,
            confidence=validation.confidence,
            status=status,
            stop_reason=state.stop_reason,
            iterations=state.iteration,
            observations=state.observations,
            total_latency_ms=state.elapsed_ms(),
        )
