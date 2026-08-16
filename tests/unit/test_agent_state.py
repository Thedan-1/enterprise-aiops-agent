import time

from app.agent.state import AgentState, ObservationRecord, PlannerDecision
from app.core.types import ToolResult


def _state(**kwargs) -> AgentState:
    defaults = dict(request_id="r1", query="q")
    defaults.update(kwargs)
    return AgentState(**defaults)


def test_stops_when_planner_says_sufficient():
    state = _state()
    decision = PlannerDecision(reasoning="", tool_name=None, tool_input=None, sufficient=True)
    stop, reason = state.should_stop(decision)
    assert stop is True
    assert reason == "planner_sufficient"


def test_continues_when_not_sufficient_and_within_limits():
    state = _state(max_iterations=5)
    decision = PlannerDecision(reasoning="", tool_name="knowledge_search", tool_input={}, sufficient=False)
    stop, reason = state.should_stop(decision)
    assert stop is False


def test_stops_at_max_iterations():
    state = _state(max_iterations=3)
    state.iteration = 3
    decision = PlannerDecision(reasoning="", tool_name="knowledge_search", tool_input={}, sufficient=False)
    stop, reason = state.should_stop(decision)
    assert stop is True
    assert reason == "max_iterations"


def test_stops_on_timeout():
    state = _state(timeout_s=0.01)
    time.sleep(0.02)
    decision = PlannerDecision(reasoning="", tool_name="knowledge_search", tool_input={}, sufficient=False)
    stop, reason = state.should_stop(decision)
    assert stop is True
    assert reason == "timeout"


def test_stops_when_tool_budget_exhausted_prevents_infinite_loop():
    """这个测试直接对应 project_management.md 的'Agent无限循环'排查树第2条：
    验证 tool_budget 真的能在 Planner 反复选同一个 Tool 时把循环切断。"""
    state = _state(max_iterations=10)
    result = ToolResult(success=True, summary="ok")
    for _ in range(2):  # 默认budget=2次
        state.record_call(state.iteration, "knowledge_search", {}, result)
        state.iteration += 1

    decision = PlannerDecision(reasoning="", tool_name="knowledge_search", tool_input={}, sufficient=False)
    stop, reason = state.should_stop(decision)
    assert stop is True
    assert reason == "tool_budget_exhausted"


def test_unknown_tool_name_none_treated_as_sufficient():
    state = _state()
    decision = PlannerDecision(reasoning="", tool_name=None, tool_input=None, sufficient=False)
    stop, reason = state.should_stop(decision)
    assert stop is True
