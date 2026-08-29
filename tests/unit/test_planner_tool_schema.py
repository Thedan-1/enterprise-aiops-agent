import json

from app.core.llm_client import PromptedLLMClient
from app.core.types import ToolSpec


class _CapturingPlanner(PromptedLLMClient):
    def __init__(self):
        self.last_user = ""

    def _call(self, system: str, user: str) -> str:
        self.last_user = user
        return json.dumps({
            "reasoning": "enough",
            "tool_name": None,
            "tool_input": {},
            "sufficient": True,
        })


def test_planner_prompt_contains_each_tools_input_contract():
    client = _CapturingPlanner()
    tools = [
        ToolSpec(
            name="ticket_search",
            description="查询工单",
            input_schema={"service": "str(optional)", "query": "str(optional)"},
        )
    ]

    client.plan_next_action("查历史工单", "diagnosis", [], tools)

    assert "input_schema" in client.last_user
    assert '"query": "str(optional)"' in client.last_user
    assert '"service": "str(optional)"' in client.last_user

