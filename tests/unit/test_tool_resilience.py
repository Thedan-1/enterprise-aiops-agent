import time

from app.agent.tools.base import Tool, TransientToolError
from app.core.types import ToolResult


class _FlakyTool(Tool):
    name = "flaky"
    description = "test"
    input_schema = {}
    max_attempts = 2
    backoff_base_s = 0

    def __init__(self):
        self.calls = 0

    def _call(self) -> ToolResult:
        self.calls += 1
        if self.calls == 1:
            raise TransientToolError("temporary upstream failure")
        return ToolResult(success=True, summary="recovered")


class _SlowTool(Tool):
    name = "slow"
    description = "test"
    input_schema = {}
    max_attempts = 1
    timeout_s = 0.01

    def _call(self) -> ToolResult:
        time.sleep(0.05)
        return ToolResult(success=True, summary="too late")


def test_tool_retries_declared_transient_failure_then_recovers():
    tool = _FlakyTool()

    result = tool.call()

    assert result.success is True
    assert result.summary == "recovered"
    assert result.debug["attempts"] == 2
    assert tool.calls == 2


def test_tool_timeout_becomes_failed_observation_instead_of_hanging_loop():
    result = _SlowTool().call()

    assert result.success is False
    assert result.error == "tool timeout after 0.01s"
    assert result.debug["attempts"] == 1
    assert result.debug["timed_out"] is True


def test_tool_rejects_unknown_input_before_adapter_execution():
    tool = _FlakyTool()

    result = tool.call(keyword="wrong-field")

    assert result.success is False
    assert "invalid tool input" in result.error
    assert "keyword" in result.error
    assert tool.calls == 0
