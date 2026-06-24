import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import get_key, set_key

# python-dotenv 對「.env 缺某 key」會記 warning；本模組每個讀取都以預設值兜底，
# 缺 key 是預期行為（全新 .env、尚未開啟的功能），故關掉這條 warning，避免控制台洗版。
logging.getLogger("dotenv").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = str(ROOT / ".env")
WEEKLYFOCUS_PATH = ROOT / "prompts" / "WeeklyFocus.md"
PROFILE_PATH = ROOT / "prompts" / "owner_profile.json"


# ── owner profile ────────────────────────────────────────────
def read_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8")) if PROFILE_PATH.exists() else {}


def write_profile(profile: dict) -> None:
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


# ── LLM 供應商金鑰（存 .env；讀取端只回布林，永不回金鑰本體）──
_LLM_KEY_VARS = {"gemini": "GEMINI_API_KEY",
                 "anthropic": "ANTHROPIC_API_KEY",
                 "openai": "OPENAI_API_KEY",
                 "tavily": "TAVILY_API_KEY"}


def read_llm_keys() -> dict:
    return {name: bool(get_key(ENV_PATH, var)) for name, var in _LLM_KEY_VARS.items()}


def write_llm_keys(keys: dict) -> None:
    for name, var in _LLM_KEY_VARS.items():
        val = (keys.get(name) or "").strip()
        if val:                       # 留空＝不變更
            set_key(ENV_PATH, var, val, quote_mode="never")


# ── Telegram Bot Token（遮罩；讀取只回是否已設定，永不回 token 本體）──
def read_bot_token_set() -> bool:
    return bool(get_key(ENV_PATH, "TG_BOT_TOKEN"))


def write_bot_token(token: str) -> None:
    token = (token or "").strip()
    if token:                         # 留空＝不變更
        set_key(ENV_PATH, "TG_BOT_TOKEN", token, quote_mode="never")


# ── 動作工具（Phase A） ───────────────────────────────────────
def read_actions() -> dict:
    return {
        "enabled": (get_key(ENV_PATH, "ACTIONS_ENABLED") or "false").lower() == "true",
        "calendar_name": get_key(ENV_PATH, "CALENDAR_NAME") or "",
        "email_enabled": (get_key(ENV_PATH, "EMAIL_ENABLED") or "false").lower() == "true",
        "mail_account": get_key(ENV_PATH, "MAIL_ACCOUNT") or "",
        "media_enabled": (get_key(ENV_PATH, "MEDIA_ENABLED") or "false").lower() == "true",
        "search_enabled": (get_key(ENV_PATH, "SEARCH_ENABLED") or "false").lower() == "true",
    }


def write_actions(enabled: bool, calendar_name: str, email_enabled: bool, mail_account: str,
                  media_enabled: bool = False, search_enabled: bool = False) -> None:
    set_key(ENV_PATH, "ACTIONS_ENABLED", "true" if enabled else "false", quote_mode="never")
    set_key(ENV_PATH, "CALENDAR_NAME", (calendar_name or "").strip(), quote_mode="never")
    set_key(ENV_PATH, "EMAIL_ENABLED", "true" if email_enabled else "false", quote_mode="never")
    set_key(ENV_PATH, "MAIL_ACCOUNT", (mail_account or "").strip(), quote_mode="never")
    set_key(ENV_PATH, "MEDIA_ENABLED", "true" if media_enabled else "false", quote_mode="never")
    set_key(ENV_PATH, "SEARCH_ENABLED", "true" if search_enabled else "false", quote_mode="never")


# 搭檔瀏覽網頁總開關（存 .env；config.BROWSE_ENABLED 同時吃 true/1）
def read_browse_enabled() -> bool:
    return (get_key(ENV_PATH, "BROWSE_ENABLED") or "false").strip().lower() in ("1", "true", "yes", "on")


def write_browse_enabled(enabled: bool) -> None:
    set_key(ENV_PATH, "BROWSE_ENABLED", "true" if enabled else "false", quote_mode="never")


# 搭檔自動配圖總開關（存 .env；config.IMAGE_GEN_ENABLED 同時吃 true/1）
def read_image_gen_enabled() -> bool:
    return (get_key(ENV_PATH, "IMAGE_GEN_ENABLED") or "false").strip().lower() in ("1", "true", "yes", "on")


def write_image_gen_enabled(enabled: bool) -> None:
    set_key(ENV_PATH, "IMAGE_GEN_ENABLED", "true" if enabled else "false", quote_mode="never")


# owner 身份（Telegram 卡設定；用於動作觸發 + 白名單自動放行）
def read_owner() -> dict:
    return {"owner_chat_id": get_key(ENV_PATH, "OWNER_CHAT_ID") or ""}


def write_owner(owner_chat_id: str) -> None:
    set_key(ENV_PATH, "OWNER_CHAT_ID", str(owner_chat_id or "").strip(), quote_mode="never")


# ── data sources（vault 路徑 + GitHub repos，存 .env）─────────
def read_sources() -> dict:
    repos_raw = get_key(ENV_PATH, "GITHUB_REPOS") or ""
    return {
        "obsidian_path": get_key(ENV_PATH, "OBSIDIAN_PATH") or "",
        "github_repos": [r.strip() for r in repos_raw.replace("\n", ",").split(",") if r.strip()],
        "code_root": get_key(ENV_PATH, "CODE_ROOT") or "",
    }


def write_sources(obsidian_path: str, github_repos, code_root: str = "") -> None:
    set_key(ENV_PATH, "OBSIDIAN_PATH", obsidian_path, quote_mode="never")
    set_key(ENV_PATH, "GITHUB_REPOS", ",".join(github_repos), quote_mode="never")
    set_key(ENV_PATH, "CODE_ROOT", code_root, quote_mode="never")


def is_on_leave() -> bool:
    """owner 今天是否在請假區間內。"""
    return read_leave().get("status", "").startswith("請假中")


# ── allowlist（id + 別名，存可攜 JSON）────────────────────────
ALLOWLIST_PATH = Path.home() / ".n" / "allowlist.json"


def read_allowlist() -> list:
    if ALLOWLIST_PATH.exists():
        return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    raw = get_key(ENV_PATH, "ALLOWLIST_USER_IDS") or ""        # 後備：舊 .env
    return [{"id": int(x), "alias": ""} for x in raw.replace(" ", "").split(",") if x.strip()]


def write_allowlist(entries) -> None:
    norm = [{"id": int(e["id"]), "alias": (e.get("alias") or "").strip()} for e in entries]
    ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_PATH.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8")


# ── models ───────────────────────────────────────────────────
def read_models() -> dict:
    return {
        "general": get_key(ENV_PATH, "MODEL_GENERAL") or "gemini-2.5-flash",
        "code": get_key(ENV_PATH, "MODEL_CODE") or "gemini-2.5-pro",
        "threshold": get_key(ENV_PATH, "RETRIEVAL_THRESHOLD") or "0.3",
        "openai_base_url": get_key(ENV_PATH, "OPENAI_BASE_URL") or "",
    }


def write_models(general: str, code: str, threshold, openai_base_url: str | None = None) -> None:
    set_key(ENV_PATH, "MODEL_GENERAL", general, quote_mode="never")
    set_key(ENV_PATH, "MODEL_CODE", code, quote_mode="never")
    set_key(ENV_PATH, "RETRIEVAL_THRESHOLD", str(threshold), quote_mode="never")
    if openai_base_url is not None:                  # 空字串＝清除（回官方端點）
        set_key(ENV_PATH, "OPENAI_BASE_URL", openai_base_url.strip(), quote_mode="never")


# ── leave / WeeklyFocus ──────────────────────────────────────
def _split_frontmatter(text: str):
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[1], parts[2].lstrip("\n")
    return "", text


def _today() -> date:
    return date.today()


def _derive_status(start: str, end: str) -> str:
    if not start or not end:
        return "在職中（目前無排定請假）"
    try:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return "在職中（目前無排定請假）"
    if s <= _today() <= e:
        back = (e + timedelta(days=1)).strftime("%Y-%m-%d")
        return f"請假中（{start} ~ {end}，預計 {back} 回來）"
    return "在職中（目前無排定請假）"


def read_leave() -> dict:
    text = WEEKLYFOCUS_PATH.read_text(encoding="utf-8") if WEEKLYFOCUS_PATH.exists() else ""
    fm, body = _split_frontmatter(text)
    start = end = ""
    for line in fm.splitlines():
        if line.startswith("leave_start:"):
            start = line.split(":", 1)[1].strip()
        elif line.startswith("leave_end:"):
            end = line.split(":", 1)[1].strip()
        elif line.startswith("return_date:") and not end:   # 舊檔遷移
            end = line.split(":", 1)[1].strip()
    return {"leave_start": start, "leave_end": end,
            "status": _derive_status(start, end), "focus": body.strip()}


def write_leave(leave_start: str, leave_end: str, focus: str) -> None:
    today = _today().strftime("%Y-%m-%d")
    fm = f"---\nupdated: {today}\nleave_start: {leave_start}\nleave_end: {leave_end}\n---\n\n"
    WEEKLYFOCUS_PATH.write_text(fm + (focus or "").strip() + "\n", encoding="utf-8")
