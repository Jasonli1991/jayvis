import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "JAYVIS"
APP_VERSION = "1.0.0"

# Telegram MTProto credentials (from https://my.telegram.org)
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION_NAME = os.getenv("TG_SESSION_NAME", "jayvis_session")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5"

# Obsidian vault path（在 .env 設 OBSIDIAN_PATH 指向自己的 vault；留空＝不用 Obsidian）
OBSIDIAN_PATH = os.getenv("OBSIDIAN_PATH", "")

# 本地資料目錄（對話記憶、白名單、legacy chroma 等可攜檔）
DATA_DIR = os.path.expanduser("~/.n")

# ChromaDB 本地儲存位置（legacy，未用於 live 檢索）
CHROMA_PATH = os.path.join(DATA_DIR, "chroma_db")

# SQLite 知識庫（取代 Postgres；單檔、零伺服器）
KB_PATH = os.getenv("KB_PATH", os.path.join(DATA_DIR, "kb.sqlite"))

# GitHub repos 要追蹤的 commit 紀錄（選用：.env 設 GITHUB_REPOS=owner/repo,... ；空字串即停用）
_GITHUB_DEFAULT = []


def _parse_repos(raw):
    if raw is None:                       # 未定義 → 用預設
        return list(_GITHUB_DEFAULT)
    return [r.strip() for r in raw.replace("\n", ",").split(",") if r.strip()]


GITHUB_REPOS = _parse_repos(os.getenv("GITHUB_REPOS"))
COMMITS_PER_REPO = 10

CODE_ROOT = os.getenv("CODE_ROOT", "")     # 本機專案母資料夾（子資料夾＝專案），供程式問答委派
CODE_MODEL = os.getenv("CODE_MODEL", "claude-opus-4-8")    # 委派用 claude CLI 模型（CLI≥2.1.178 後 4-8 可用）
CODE_ASK_BUDGET_USD = float(os.getenv("CODE_ASK_BUDGET_USD", "2.0"))      # A/B 問答/計畫預算（Opus 較貴，給足）
CODE_APPLY_BUDGET_USD = float(os.getenv("CODE_APPLY_BUDGET_USD", "15.0")) # C1 改碼+測試+開 PR 預算（Opus 思考較吃）

# TG 訊息同步設定
TG_SYNC_DAYS = 7  # 抓幾天以內的訊息

# 要同步的群組標題（依你的 Telegram 群組名稱填寫）
TG_SYNC_GROUPS = [
    # "Your Team Group",
]

# 要同步的聯絡人顯示名稱（依你的 Telegram 聯絡人填寫）
TG_SYNC_CONTACTS = [
    # "Teammate Name",
]

# 私訊白名單：只回覆 TG_SYNC_CONTACTS 名單內的人，其他人不回
REPLY_WHITELIST_ONLY = True

# 請假模式：True 才會自動回覆
VACATION_MODE = False

# 回覆前隨機延遲秒數（模擬真人打字）
REPLY_DELAY_MIN = 2
REPLY_DELAY_MAX = 6

# ── 擁有者身份檔（多租戶化）──────────────────────────────────────────
# 使用者透過控制台寫入 owner_profile.json；未設定時退回 .example 範本。
_PROFILE_PATH = Path(__file__).parent / "prompts" / "owner_profile.json"
_PROFILE_EXAMPLE_PATH = Path(__file__).parent / "prompts" / "owner_profile.example.json"


def _load_profile() -> dict:
    for _p in (_PROFILE_PATH, _PROFILE_EXAMPLE_PATH):
        try:
            if _p.exists():
                return json.loads(_p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


_PROFILE = _load_profile()
OWNER_NAME = _PROFILE.get("owner_name") or os.getenv("OWNER_NAME", "Owner")
# 知識庫單一 owner 標籤（單庫單人、無分區）。固定內部值，與 schema/ingest/檢索預設一致；
# 純內部 DB 分區鍵，不對外顯示。
OWNER_KEY = "owner"

# ── Bot API 助理（Phase 2）─────────────────────────────────────────────
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
ASSISTANT_NAME = _PROFILE.get("assistant_name") or os.getenv("ASSISTANT_NAME", APP_NAME)

# ── 動作工具（Phase A）：預設全關，分享出去才安全 ──────────────
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "0"))      # 唯一能觸發動作的 TG id；0＝關
ACTIONS_ENABLED = os.getenv("ACTIONS_ENABLED", "false").lower() == "true"
CALENDAR_NAME = os.getenv("CALENDAR_NAME", "")            # 目標日曆；空＝第一本
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"   # 發信/讀信總開關（獨立）
MAIL_ACCOUNT = os.getenv("MAIL_ACCOUNT", "")                            # 預設寄件帳號；空＝發信時問
MEDIA_ENABLED = os.getenv("MEDIA_ENABLED", "false").lower() == "true"   # 圖片/文件工具總開關（獨立）


def _parse_ids(s: str) -> set[int]:
    return {int(x) for x in s.replace(" ", "").split(",") if x.strip()}


# 白名單改用可攜 JSON（id→別名）；首次自動從舊 .env 的 ALLOWLIST_USER_IDS 遷移
ALLOWLIST_PATH = Path(os.getenv("ALLOWLIST_PATH",
                                os.path.join(DATA_DIR, "allowlist.json")))


def _load_allowlist():
    if ALLOWLIST_PATH.exists():
        entries = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    else:
        entries = [{"id": i, "alias": ""}
                   for i in sorted(_parse_ids(os.getenv("ALLOWLIST_USER_IDS", "")))]
        if entries:
            ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            ALLOWLIST_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    ids = {int(e["id"]) for e in entries}
    aliases = {int(e["id"]): e.get("alias", "") for e in entries}
    return ids, aliases


ALLOWLIST_USER_IDS, ALLOWLIST_ALIASES = _load_allowlist()

# ── LLM 供應商 / 路由（Phase 3）─────────────────────────────────────────
GCP_PROJECT = os.getenv("GCP_PROJECT", "")
GCP_LOCATION = os.getenv("GCP_LOCATION", "global")
# 同事用：設了 GEMINI_API_KEY 就走 Gemini Developer API（免 GCP），否則用 Vertex
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# 多供應商：模型名 claude-* 走 Anthropic、gpt-*/o* 走 OpenAI（金鑰沒設則該家不可用）
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# OpenAI 相容第三方端點（如 siraya）：設了之後，非 gemini-*/claude-* 模型一律走此端點
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
MODEL_GENERAL = os.getenv("MODEL_GENERAL", "gemini-2.5-flash")
MODEL_CODE = os.getenv("MODEL_CODE", "gemini-2.5-pro")
# 記憶層：近期歷史輪數、語意回想筆數、進語意庫的最短字數
MEMORY_RECENT_TURNS = int(os.getenv("MEMORY_RECENT_TURNS", "10"))
MEMORY_RECALL_N = int(os.getenv("MEMORY_RECALL_N", "6"))
MEMORY_MIN_CHARS = int(os.getenv("MEMORY_MIN_CHARS", "6"))
# 時事搜尋（Tavily）：開關 + 金鑰；兩者備齊才會搜
SEARCH_ENABLED = os.getenv("SEARCH_ENABLED", "false").lower() == "true"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
