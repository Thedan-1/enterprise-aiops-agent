"""Input guard for obvious abuse; authorization is still enforced separately."""
import re
from dataclasses import dataclass


MAX_QUERY_CHARS = 4000
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"忽略(之前|以上|所有).{0,8}(指令|要求)",
    r"(reveal|show|print).{0,20}system\s+prompt",
    r"(输出|展示|泄露).{0,12}(系统提示词|system prompt)",
    r"act\s+as\s+(an?\s+)?admin",
]


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str = ""


def inspect_query(query: str) -> GuardResult:
    cleaned = query.strip()
    if not cleaned:
        return GuardResult(False, "问题不能为空")
    if len(cleaned) > MAX_QUERY_CHARS:
        return GuardResult(False, f"问题超过 {MAX_QUERY_CHARS} 字符限制")
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            return GuardResult(False, "检测到试图覆盖系统规则的提示词注入")
    return GuardResult(True)

