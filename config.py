import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int_env(key: str, default: int) -> int:
    """讀環境變數轉 int；未設定或留空（含只有空白）一律退回 default。

    注意：os.getenv(key, "0") 的預設只在 key 不存在時生效；key 存在但值為空字串
    （.env 寫 OWNER_CHAT_ID= 即如此）會回 ''，int('') 會 ValueError。此包裝把空值視同未設定。
    """
    raw = (os.getenv(key) or "").strip()
    return int(raw) if raw else default


def _float_env(key: str, default: float) -> float:
    """同 _int_env，轉 float。"""
    raw = (os.getenv(key) or "").strip()
    return float(raw) if raw else default


def _str_env(key: str, default: str) -> str:
    """同 _int_env，字串版：未設定或留空一律退回 default。
    用於不該為空的值（如模型名——面板存模型卡時欄位空白會寫成 KEY=，空模型會讓 bot 挑不到模型）。"""
    raw = (os.getenv(key) or "").strip()
    return raw if raw else default


APP_NAME = "JAYVIS"
APP_VERSION = "1.0.0"

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Obsidian vault path（在 .env 設 OBSIDIAN_PATH 指向自己的 vault；留空＝不用 Obsidian）
OBSIDIAN_PATH = os.getenv("OBSIDIAN_PATH", "")
# 分析模式 HTML 報告：報告較長 → 大 token；撈更多 KB 以求詳盡（皆可 env 覆蓋）
ANALYSIS_REPORT_MAX_TOKENS = _int_env("ANALYSIS_REPORT_MAX_TOKENS", 16000)
ANALYSIS_REPORT_K = _int_env("ANALYSIS_REPORT_K", 60)
ANALYSIS_REPORT_MAX_CONTEXT = _int_env("ANALYSIS_REPORT_MAX_CONTEXT", 40000)

# 本地資料目錄（對話記憶、白名單等可攜檔）
DATA_DIR = os.path.expanduser("~/.n")

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
CODE_ASK_BUDGET_USD = _float_env("CODE_ASK_BUDGET_USD", 2.0)      # A/B 問答/計畫預算（Opus 較貴，給足）
CODE_APPLY_BUDGET_USD = _float_env("CODE_APPLY_BUDGET_USD", 15.0) # C1 改碼+測試+開 PR 預算（Opus 思考較吃）


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

# ── Bot API 搭檔（Phase 2）─────────────────────────────────────────────
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
ASSISTANT_NAME = _PROFILE.get("assistant_name") or os.getenv("ASSISTANT_NAME", APP_NAME)

# ── 動作工具（Phase A）：預設全關，分享出去才安全 ──────────────
OWNER_CHAT_ID = _int_env("OWNER_CHAT_ID", 0)      # 唯一能觸發動作的 TG id；0＝關（留空亦同）
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
MODEL_GENERAL = _str_env("MODEL_GENERAL", "gemini-2.5-flash")   # 空值（面板存空欄位）退回預設，避免 bot 挑不到模型
MODEL_CODE = _str_env("MODEL_CODE", "gemini-2.5-pro")
# 記憶層：近期歷史輪數、語意回想筆數、進語意庫的最短字數
MEMORY_RECENT_TURNS = _int_env("MEMORY_RECENT_TURNS", 10)
MEMORY_RECALL_N = _int_env("MEMORY_RECALL_N", 6)
MEMORY_MIN_CHARS = _int_env("MEMORY_MIN_CHARS", 6)
# 時事搜尋（Tavily）：開關 + 金鑰；兩者備齊才會搜
SEARCH_ENABLED = os.getenv("SEARCH_ENABLED", "false").lower() == "true"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ── 搭檔瀏覽網頁（借用已登入 Chrome）──────────────────────────
BROWSE_ENABLED = os.getenv("BROWSE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
BROWSE_CDP_URL = os.getenv("BROWSE_CDP_URL", "http://localhost:9222")
BROWSE_MAX_STEPS = _int_env("BROWSE_MAX_STEPS", 12)
# 預設跟隨一般模型（用你已設定、有額度的供應商；不寫死昂貴模型）；要更強推理可自行設 BROWSE_MODEL
BROWSE_MODEL = os.getenv("BROWSE_MODEL", "") or MODEL_GENERAL
BROWSE_NAV_TIMEOUT_S = _int_env("BROWSE_NAV_TIMEOUT_S", 30)
BROWSE_TMP_DIR = os.getenv("BROWSE_TMP_DIR", os.path.expanduser("~/.n/browse_tmp"))
# 導航後等頁面算繪穩定（SPA 客戶端渲染），避免黑圖/空文字：networkidle 上限 + 固定 settle
BROWSE_SETTLE_TIMEOUT_S = _float_env("BROWSE_SETTLE_TIMEOUT_S", 2.5)
BROWSE_SETTLE_MS = _int_env("BROWSE_SETTLE_MS", 1000)
# 專用瀏覽設定檔（獨立 Chrome instance，與個人 Chrome 隔離；第一次需在該視窗登入要用的站）
BROWSE_PROFILE_DIR = os.getenv("BROWSE_PROFILE_DIR", os.path.expanduser("~/.n/chrome-browse-profile"))

# ── 搭檔自動配圖（Pollinations.AI）──────────────────────────
IMAGE_GEN_ENABLED = os.getenv("IMAGE_GEN_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL", "flux")
IMAGE_GEN_SIZE = _int_env("IMAGE_GEN_SIZE", 1024)
IMAGE_GEN_TIMEOUT_S = _int_env("IMAGE_GEN_TIMEOUT_S", 45)
IMAGE_GEN_FONT = os.getenv("IMAGE_GEN_FONT", "")    # 梗圖字幕字型（空＝自動找系統中文字型）


def reload_runtime_keys(env_path: str | None = None) -> None:
    """面板存檔/重啟後免關掉整個面板即生效：重新從 .env 刷新「面板會即時用到」的設定到 config
    —— LLM 金鑰/端點 + 一般/高階模型名（這些值在啟動時載入，之後 load_dotenv 不重讀）。
    不動其他啟動期設定（那些由 bot 子行程重啟時經 _bot_env 取得新值）。"""
    from dotenv import dotenv_values
    env = dotenv_values(env_path or os.path.join(os.path.dirname(__file__), ".env"))

    def g(k, default=""):
        v = (env.get(k) or "").strip()
        return v if v else default

    global GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL
    global GCP_PROJECT, GCP_LOCATION, TAVILY_API_KEY, MODEL_GENERAL, MODEL_CODE
    GEMINI_API_KEY = g("GEMINI_API_KEY")
    ANTHROPIC_API_KEY = g("ANTHROPIC_API_KEY")
    OPENAI_API_KEY = g("OPENAI_API_KEY")
    OPENAI_BASE_URL = g("OPENAI_BASE_URL")
    GCP_PROJECT = g("GCP_PROJECT")
    GCP_LOCATION = g("GCP_LOCATION", "global")
    TAVILY_API_KEY = g("TAVILY_API_KEY")
    MODEL_GENERAL = g("MODEL_GENERAL", "gemini-2.5-flash")   # 空值退回預設（同 _str_env）
    MODEL_CODE = g("MODEL_CODE", "gemini-2.5-pro")
