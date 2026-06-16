import re
from dataclasses import dataclass

# 硬密鑰：命中即整塊不存
_BLOCK_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic_secret": re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9/\+_\-]{16,}"),
}

# PII：遮罩但不阻擋
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\b09\d{8}\b")  # 台灣手機


@dataclass
class Sanitized:
    text: str
    blocked: bool
    reasons: list[str]


def sanitize(text: str) -> Sanitized:
    reasons = [name for name, pat in _BLOCK_PATTERNS.items() if pat.search(text)]
    if reasons:
        return Sanitized(text="", blocked=True, reasons=reasons)
    masked = _EMAIL.sub("[email]", text)
    masked = _PHONE.sub("[phone]", masked)
    return Sanitized(text=masked, blocked=False, reasons=[])
