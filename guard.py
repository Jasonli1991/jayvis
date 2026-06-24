import re

# 常見 prompt injection 特徵詞（中英文）
_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"forget\s+(everything|all)",
    r"system\s*prompt",
    r"你(現在是|是一個新的|要扮演|要假裝)",
    r"忽略.{0,10}(指令|規則|設定|上面)",
    r"假裝你是",
    r"扮演.{0,10}(角色|AI|機器人|助理|搭檔)",
    r"切換.{0,10}(模式|角色|身份)",
    r"(開發者|developer|dan|jailbreak).{0,10}模式",
    r"reveal\s+(your\s+)?(prompt|instructions?|system)",
    r"show\s+(me\s+)?(your\s+)?(prompt|instructions?|system)",
    r"透露.{0,10}(指令|提示|設定|system)",
    r"你的.{0,5}(系統提示|指令|設定|prompt)",
    r"act\s+as\s+(if|a|an)",
    r"pretend\s+(to\s+be|you\s+are)",
    r"roleplay",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def is_injection(text: str) -> bool:
    """回傳 True 表示偵測到 prompt injection 嘗試。"""
    for pattern in _COMPILED:
        if pattern.search(text):
            return True
    return False
