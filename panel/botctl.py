import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

import config
from db.connection import get_conn

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / ".bot.pid"
LOG_FILE = ROOT / "bot.log"


def is_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _bot_env() -> dict:
    """bot 子行程的環境：以當前 .env 蓋過繼承來的舊變數。
    否則面板早期啟動時的舊 MODEL_*/金鑰會被子行程繼承，且 load_dotenv(override=False)
    不會用新 .env 覆蓋 → 重啟後仍跑舊設定。"""
    env = dict(os.environ)
    env.update({k: v for k, v in dotenv_values(str(ROOT / ".env")).items() if v is not None})
    return env


def _model_ready(model: str, g) -> tuple[bool, str]:
    """比照 llm._provider_of 的路由，判斷『一般模型』對應供應商是否備齊金鑰/端點。
    g 為現讀 .env 的取值器。回 (是否可用, 缺什麼的說明)。"""
    m = (model or "").lower()
    if m.startswith("claude"):
        return bool(g("ANTHROPIC_API_KEY")), "一般模型是 claude-*，需要 Anthropic 金鑰（ANTHROPIC_API_KEY）"
    if m.startswith("gpt") or m.startswith("o"):
        return (bool(g("OPENAI_API_KEY") or g("OPENAI_BASE_URL")),
                "一般模型是 gpt-*/o*，需要 OpenAI 金鑰（OPENAI_API_KEY）或相容端點（OPENAI_BASE_URL）")
    if m.startswith("gemini"):
        return (bool(g("GEMINI_API_KEY") or g("GCP_PROJECT")),
                "一般模型是 gemini-*，需要 Google 金鑰（GEMINI_API_KEY）或 GCP 專案（GCP_PROJECT）")
    if g("OPENAI_BASE_URL"):
        return True, ""        # 未知前綴 + 有相容端點（本地 Ollama 等）→ 免金鑰
    return (bool(g("GEMINI_API_KEY") or g("GCP_PROJECT")),
            f"一般模型「{model}」未設 OPENAI_BASE_URL 會走 Google，"
            "需要 GEMINI_API_KEY 或 GCP_PROJECT，或設 OPENAI_BASE_URL 走本地/相容端點")


def preflight_errors(env_path: str | None = None) -> list[str]:
    """啟動前檢查最低必要設定。現讀 .env（與 _bot_env 同步），不用面板可能過時的 config.*。
    回人類可讀的問題清單；空清單＝可啟動。"""
    env = dotenv_values(env_path or str(ROOT / ".env"))

    def g(k):
        return (env.get(k) or "").strip()

    problems = []
    if not g("TG_BOT_TOKEN"):
        problems.append("缺 Telegram Bot Token —— 請在「Telegram」卡填入（向 @BotFather 建 bot 取得）")
    model = g("MODEL_GENERAL") or "gemini-2.5-flash"   # 與 config 預設一致
    ok, why = _model_ready(model, g)
    if not ok:
        problems.append(why + " —— 請在「模型」卡設定")
    return problems


def start() -> None:
    if is_running():
        return
    logf = open(LOG_FILE, "a")
    p = subprocess.Popen([sys.executable, "bot.py"], cwd=str(ROOT),
                         stdout=logf, stderr=subprocess.STDOUT, env=_bot_env())
    PID_FILE.write_text(str(p.pid))


def stop() -> None:
    if not PID_FILE.exists():
        return
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        PID_FILE.unlink(missing_ok=True)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        PID_FILE.unlink(missing_ok=True)
        return
    # 等舊 bot 真的結束再回（最多 ~8s）。否則重啟時新舊兩隻會搶 Telegram long-poll（409 衝突）
    # → bot 看似沒套用新設定，使用者只好整個關掉面板重開。
    for _ in range(40):
        try:
            os.kill(pid, 0)            # 0 號訊號＝只探測是否還活著
        except OSError:
            break                      # 已結束
        time.sleep(0.2)
    else:
        try:
            os.kill(pid, signal.SIGKILL)   # 逾時仍沒死 → 強制結束
        except Exception:
            pass
    PID_FILE.unlink(missing_ok=True)


def restart() -> None:
    stop()                # stop() 已等舊行程結束，不必再固定 sleep
    start()


def log_event(msg: str) -> None:
    """面板側事件寫進同一個 bot.log（重啟/分析等），讓「即時 Log」也看得到。
    格式比照 bot 的 logging（INFO:來源:訊息），方便 tail_log 一致顯示。"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"INFO:panel:{msg}\n")
    except Exception:
        pass


# 噪音行：telegram 輪詢（也洩漏 bot token）、模型載入進度條
_LOG_NOISE = ("api.telegram.org", "Batches:", "sentence_transformers", "pytorch device")


def _collapse_tracebacks(lines: list) -> list:
    """把多行 Python traceback 收摺成一行重點（取最後的例外摘要）。
    只用於面板顯示（clean）；原始 bot.log 不動，完整 traceback 仍在檔案備查。"""
    out = []
    i, n = 0, len(lines)
    while i < n:
        if lines[i].strip() == "Traceback (most recent call last):":
            j = i + 1
            # 跳過框架行（縮排的 File.../程式碼）與空行，停在例外摘要那一行（非縮排）
            while j < n and (lines[j][:1] in (" ", "\t") or not lines[j].strip()):
                j += 1
            summary = lines[j].strip() if j < n else "（未知錯誤）"
            out.append("⚠️ " + summary)
            i = j + 1
        else:
            out.append(lines[i])
            i += 1
    return out


def tail_log(n: int = 200, clean: bool = False) -> str:
    if not LOG_FILE.exists():
        return ""
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if clean:
        lines = _collapse_tracebacks(lines)        # 先把 traceback 收成一行
        lines = [ln for ln in lines if ln.strip() and not any(p in ln for p in _LOG_NOISE)]
    return "\n".join(lines[-n:])


def _memory_counts() -> dict:
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT source_type, count(*) AS n FROM chunks GROUP BY source_type"
        ).fetchall()
        conn.close()
        return {r["source_type"]: r["n"] for r in rows}
    except Exception:
        return {}


def status() -> dict:
    return {
        "running": is_running(),
        "models": {"general": config.MODEL_GENERAL, "code": config.MODEL_CODE},
        "allowlist": len(config.ALLOWLIST_USER_IDS),
        "memory": _memory_counts(),
    }
