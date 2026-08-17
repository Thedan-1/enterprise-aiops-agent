"""Answer Validator：证据校验 + 置信度评估。

不是让LLM自己声称"我很确信"（LLM对自己输出的置信度自评不可靠，这是已知问题），
而是基于客观可数的信号计算置信度：是否有knowledge_search证据、是否有实时
Tool观察支撑、是否所有相关Tool都成功返回。这是"避免幻觉"这一要求在
代码里的具体落点——见 architecture.md 第0节设计原则。

ADR-007（2026-08-17，真实DeepSeek联调发现的问题的修复）：单纯"有没有evidence"
不够——Reranker分数刚好压线通过阈值、但主题和问题完全不相关的证据，会让这里
误判为"有知识库证据"，导致status判成answered，但回答正文其实在说"证据不足"，
status和回答内容对不上。加了一次Evidence Relevance判断（is_evidence_relevant，
见llm_client.py），只有证据被判定为"真的能支撑回答"才计入has_kb_evidence。
代价是真实Provider下多了一次LLM调用（延迟/成本），MockLLM走词面重合度启发式
不产生额外调用。
"""
from dataclasses import dataclass

from app.agent.state import ObservationRecord
from app.core.llm_client import LLMClient


@dataclass
class ValidationResult:
    confidence: float  # 0~1
    grounded: bool  # 是否有实际证据支撑，false则应该在Answer里明确说明证据不足
    reason: str


def validate(query: str, observations: list[ObservationRecord], llm_client: LLMClient) -> ValidationResult:
    successful = [o for o in observations if o.result.success]
    any_failure = any(not o.result.success for o in observations)

    kb_obs = [o for o in successful if o.tool_name == "knowledge_search" and o.result.evidence]
    has_kb_evidence = False
    if kb_obs:
        evidence_texts = [e.content for o in kb_obs for e in o.result.evidence]
        has_kb_evidence = llm_client.is_evidence_relevant(query, evidence_texts)

    has_realtime_evidence = any(o.tool_name in ("service_metrics", "log_query") for o in successful) or any(
        o.tool_name == "ticket_search" and o.result.debug and o.result.debug.get("tickets") for o in successful
    )

    if not successful:
        return ValidationResult(confidence=0.0, grounded=False, reason="所有工具调用均失败或无观察")

    if not has_kb_evidence and not has_realtime_evidence:
        reason = "无相关知识库证据也无实时观察数据" if not kb_obs else "检索到的证据经相关性校验后判定与问题不相关"
        return ValidationResult(confidence=0.1, grounded=False, reason=reason)

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
