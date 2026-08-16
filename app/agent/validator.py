"""Answer Validator：证据校验 + 置信度评估。

不是让LLM自己声称"我很确信"（LLM对自己输出的置信度自评不可靠，这是已知问题），
而是基于客观可数的信号计算置信度：是否有knowledge_search证据、是否有实时
Tool观察支撑、是否所有相关Tool都成功返回。这是"避免幻觉"这一要求在
代码里的具体落点——见 architecture.md 第0节设计原则。
"""
from dataclasses import dataclass

from app.agent.state import ObservationRecord


@dataclass
class ValidationResult:
    confidence: float  # 0~1
    grounded: bool  # 是否有实际证据支撑，false则应该在Answer里明确说明证据不足
    reason: str


def validate(observations: list[ObservationRecord]) -> ValidationResult:
    successful = [o for o in observations if o.result.success]
    has_kb_evidence = any(o.tool_name == "knowledge_search" and o.result.evidence for o in successful)
    has_realtime_evidence = any(o.tool_name in ("service_metrics", "log_query") for o in successful)
    any_failure = any(not o.result.success for o in observations)

    if not successful:
        return ValidationResult(confidence=0.0, grounded=False, reason="所有工具调用均失败或无观察")

    if not has_kb_evidence and not has_realtime_evidence:
        return ValidationResult(confidence=0.1, grounded=False, reason="无知识库证据也无实时观察数据")

    score = 0.3
    if has_kb_evidence:
        score += 0.35
    if has_realtime_evidence:
        score += 0.35
    if any_failure:
        score -= 0.15  # 部分工具失败,证据链不完整,适当降低置信度
    score = max(0.0, min(1.0, score))

    grounded = has_kb_evidence or has_realtime_evidence
    reason = f"kb_evidence={has_kb_evidence}, realtime_evidence={has_realtime_evidence}, partial_failure={any_failure}"
    return ValidationResult(confidence=round(score, 2), grounded=grounded, reason=reason)
