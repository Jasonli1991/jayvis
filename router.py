import config

# 程式/技術深問特徵（中英）
_CODE_KEYWORDS = (
    "code", "bug", "error", "exception", "function", "api", "deploy", "build",
    "commit", "pr ", "merge", "refactor", "stack trace", "traceback", "sql",
    "程式", "報錯", "錯誤", "例外", "函式", "部署", "編譯", "重構", "資料庫",
    "後端", "前端", "套件", "相依", "環境變數", "實作", "邏輯", "怎麼運作", "修正",
)


def choose_model(query: str, source_types: list[str] | None = None) -> str:
    q = (query or "").lower()
    if any(k in q for k in _CODE_KEYWORDS):
        return config.MODEL_CODE
    # 檢索到任何 git 來源（commit/code）→ 視為技術題，走較強模型
    if source_types and any(s == "git" for s in source_types):
        return config.MODEL_CODE
    return config.MODEL_GENERAL
