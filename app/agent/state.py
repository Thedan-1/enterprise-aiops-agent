"""Agent State + Stop Condition。

关键设计：should_stop() 是纯函数，只依据结构化字段(sufficient/iteration/timeout/budget)
判断，不解析LLM的自由文本。这样 Stop Condition 可以脱离LLM单独写单测、可复现，
解决"Agent自主决策"和"回归测试可复现性"之间的张力（见 architecture.md 第0节）。
"""
import time
from dataclasses import dataclass, field

from app.core.types import ToolResult


@dataclass
class PlannerDecision:
    reasoning: str
    tool_name: str | None
    tool_input: dict | None
    sufficient: bool


@dataclass
class ObservationRecord:
    iteration: int
    tool_name: str
    tool_input: dict
    result: ToolResult


@dataclass
class AgentState:
    request_id: str
    query: str
    intent: str = "unknown"
    iteration: int = 0
    max_iterations: int = 5
    tool_budget: dict[str, int] = field(default_factory=dict)
    observations: list[ObservationRecord] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    timeout_s: float = 30.0
    status: str = "running"  # running/answered/abstained/timeout/error
    stop_reason: str = ""

    def remaining_budget(self, tool_name: str) -> int:
        return self.tool_budget.get(tool_name, 2)

    def record_call(self, iteration: int, tool_name: str, tool_input: dict, result: ToolResult) -> None:
        self.observations.append(
            ObservationRecord(iteration=iteration, tool_name=tool_name, tool_input=tool_input, result=result)
        )
        self.tool_budget[tool_name] = self.remaining_budget(tool_name) - 1

    def should_stop(self, decision: PlannerDecision) -> tuple[bool, str]:
        if decision.sufficient or decision.tool_name is None:
            return True, "planner_sufficient"
        if self.iteration >= self.max_iterations:
            return True, "max_iterations"
        if time.time() - self.start_time > self.timeout_s:
            return True, "timeout"
        if self.remaining_budget(decision.tool_name) <= 0:
            return True, "tool_budget_exhausted"
        return False, ""

    def elapsed_ms(self) -> float:
        return (time.time() - self.start_time) * 1000
