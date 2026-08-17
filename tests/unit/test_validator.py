from app.agent.state import ObservationRecord
from app.agent.validator import validate
from app.core.llm_client import MockLLMClient
from app.core.types import Evidence, ToolResult


class _StubLLM(MockLLMClient):
    """继承MockLLMClient只是为了偷懒拿到classify_intent/plan_next_action等其他抽象方法的实现，
    这里只关心 is_evidence_relevant 的返回值可控。"""

    def __init__(self, relevant: bool):
        self._relevant = relevant

    def is_evidence_relevant(self, query: str, evidence_texts: list[str]) -> bool:
        return self._relevant


def _kb_observation(evidence: list[Evidence]) -> ObservationRecord:
    return ObservationRecord(
        iteration=0, tool_name="knowledge_search", tool_input={},
        result=ToolResult(success=True, summary="found", evidence=evidence),
    )


def _realtime_observation(tool_name: str, success: bool = True) -> ObservationRecord:
    return ObservationRecord(
        iteration=1, tool_name=tool_name, tool_input={},
        result=ToolResult(success=success, summary="ok" if success else "", error=None if success else "boom"),
    )


def test_no_observations_returns_zero_confidence():
    result = validate("query", [], _StubLLM(relevant=True))
    assert result.grounded is False
    assert result.confidence == 0.0


def test_kb_evidence_relevant_grounds_and_boosts_confidence():
    obs = [_kb_observation([Evidence(chunk_id="c1", content="502相关文档", source="doc", score=0.7)])]
    result = validate("订单服务502", obs, _StubLLM(relevant=True))
    assert result.grounded is True
    assert result.confidence > 0.1


def test_kb_evidence_present_but_irrelevant_does_not_ground():
    """这是ADR-007要修的那个bug的回归测试：证据存在但主题不相关时不能算grounded。"""
    obs = [_kb_observation([Evidence(chunk_id="c1", content="年假申请文档", source="doc", score=0.51)])]
    result = validate("公司的年假申请流程是什么", obs, _StubLLM(relevant=False))
    assert result.grounded is False
    assert result.confidence == 0.1


def test_realtime_evidence_alone_grounds_without_kb():
    obs = [_realtime_observation("service_metrics")]
    result = validate("q", obs, _StubLLM(relevant=False))
    assert result.grounded is True


def test_partial_tool_failure_lowers_confidence():
    obs_ok = [_kb_observation([Evidence(chunk_id="c1", content="x", source="d", score=0.7)])]
    obs_with_failure = obs_ok + [_realtime_observation("log_query", success=False)]

    result_clean = validate("q", obs_ok, _StubLLM(relevant=True))
    result_partial = validate("q", obs_with_failure, _StubLLM(relevant=True))
    assert result_partial.confidence < result_clean.confidence
