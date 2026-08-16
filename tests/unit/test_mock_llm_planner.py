from app.agent.state import ObservationRecord
from app.core.llm_client import MockLLMClient
from app.core.types import ToolResult, ToolSpec

TOOLS = [
    ToolSpec(name="knowledge_search", description="", input_schema={}),
    ToolSpec(name="service_metrics", description="", input_schema={}),
    ToolSpec(name="log_query", description="", input_schema={}),
]


def test_classify_intent_diagnosis_keywords():
    llm = MockLLMClient()
    assert llm.classify_intent("订单服务大量502") == "diagnosis"
    assert llm.classify_intent("什么是缓存穿透") == "knowledge_qa"


def test_planner_calls_knowledge_search_first():
    llm = MockLLMClient()
    decision = llm.plan_next_action("订单服务大量502，order-service", "diagnosis", [], TOOLS)
    assert decision.tool_name == "knowledge_search"
    assert decision.sufficient is False


def test_planner_eventually_becomes_sufficient_within_tool_count():
    """回归测试：验证Mock Planner在有限步内一定会停止,不会无限循环。"""
    llm = MockLLMClient()
    observations = []
    query = "order-service最近502很多"
    for i in range(10):
        decision = llm.plan_next_action(query, "diagnosis", observations, TOOLS)
        if decision.sufficient:
            break
        observations.append(
            ObservationRecord(
                iteration=i, tool_name=decision.tool_name, tool_input=decision.tool_input or {},
                result=ToolResult(success=True, summary="服务状态异常: 错误率上升"),
            )
        )
    else:
        raise AssertionError("Planner未在10步内收敛,可能存在无限循环风险")
    assert decision.sufficient is True


def test_knowledge_qa_intent_stops_after_single_kb_search():
    llm = MockLLMClient()
    obs = [
        ObservationRecord(
            iteration=0, tool_name="knowledge_search", tool_input={},
            result=ToolResult(success=True, summary="检索到2条相关证据"),
        )
    ]
    decision = llm.plan_next_action("什么是缓存穿透", "knowledge_qa", obs, TOOLS)
    assert decision.sufficient is True
