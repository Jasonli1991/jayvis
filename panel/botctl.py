import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import dotenv_values

import config
from db.connection import get_conn

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / ".bot.pid"
LOG_FILE = ROOT / "bot.log"

# Flask threaded=True 下 /api/bot/{start,stop,restart} 可並發；序列化這些操作，
# 避免 start/stop/restart 交錯造成 .bot.pid 與實際行程不一致、spawn 出殺不掉的孤兒。
# 用 RLock 讓 restart()（內部呼叫 stop()+start()）可重入。
_op_lock = threading.RLock()

_IS_WIN = (os.name == "nt")


def _pid_alive(pid: int) -> bool:
    """跨平台探測行程是否還活著。Unix 用 os.kill(pid,0)；Windows 用 tasklist
    （Windows 的 os.kill 沒有『0 號訊號探測』語意，會直接終止行程，不能拿來探活）。"""
    if _IS_WIN:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, errors="ignore").stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate(pid: int, force: bool = False) -> None:
    """跨平台結束行程。Unix：SIGTERM／SIGKILL；Windows：taskkill /PID [/F]。"""
    if _IS_WIN:
        subprocess.run(["taskkill", "/PID", str(pid)] + (["/F"] if force else []),
                       capture_output=True)
    else:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)


def is_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return False
    return _pid_alive(pid)


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
    with _op_lock:
        if is_running():
            return
        logf = open(LOG_FILE, "a")
        p = subprocess.Popen([sys.executable, "bot.py"], cwd=str(ROOT),
                             stdout=logf, stderr=subprocess.STDOUT, env=_bot_env())
        PID_FILE.write_text(str(p.pid))


def stop() -> None:
    with _op_lock:
        if not PID_FILE.exists():
            return
        try:
            pid = int(PID_FILE.read_text().strip())
        except Exception:
            PID_FILE.unlink(missing_ok=True)
            return
        try:
            _terminate(pid)                # Unix：SIGTERM；Windows：taskkill /PID
        except Exception:
            PID_FILE.unlink(missing_ok=True)
            return
        # 等舊 bot 真的結束再回（最多 ~8s）。否則重啟時新舊兩隻會搶 Telegram long-poll（409 衝突）
        # → bot 看似沒套用新設定，使用者只好整個關掉面板重開。
        for _ in range(40):
            if not _pid_alive(pid):
                break                      # 已結束
            time.sleep(0.2)
        else:
            try:
                _terminate(pid, force=True)   # 逾時仍沒死 → 強制結束（Unix SIGKILL／Windows taskkill /F）
            except Exception:
                pass
        PID_FILE.unlink(missing_ok=True)


def restart() -> None:
    with _op_lock:        # RLock 可重入；stop()/start() 內層再取同把鎖不會卡死
        stop()            # stop() 已等舊行程結束，不必再固定 sleep
        start()


def log_event(msg: str) -> None:
    """面板側事件寫進同一個 bot.log（重啟/分析等），讓「即時 Log」也看得到。
    格式比照 bot 的 logging（時間｜INFO:來源:訊息），方便 tail_log 一致顯示。"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')}｜INFO:panel:{msg}\n")
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


def _owner_turns() -> int:
    """owner 與 JAYVIS 的對話則數（user+assistant）。供面板 logo 成長階段彩蛋判斷。
    註：此值非單調——記憶整併會把舊對話壓成摘要、刪掉原始列，所以會回落；
    「學士」用持久化的畢業里程碑（_owner_graduated）latch，不受此回落影響。"""
    try:
        conn = get_conn()
        n = conn.execute(
            "SELECT count(*) AS n FROM memories WHERE person_id=:p AND kind IN ('user','assistant')",
            {"p": str(config.OWNER_CHAT_ID)}).fetchone()["n"]
        conn.close()
        return n
    except Exception:
        return 0


_GRADUATE_AT = 100                                   # owner 對談累積達此數 → 永久「學士」
_MILESTONES = Path(config.DATA_DIR) / "milestones.json"


def _read_milestones() -> dict:
    try:
        return json.loads(_MILESTONES.read_text(encoding="utf-8")) if _MILESTONES.exists() else {}
    except Exception:
        return {}


def _owner_graduated(turns: int) -> bool:
    """owner 對談累積『曾經』達門檻 → 永久學士里程碑（持久化）。一旦畢業，之後記憶整併
    把 count 壓回也維持學士（畢業了就不會變回學生）。"""
    if _read_milestones().get("owner_graduated"):
        return True
    if turns >= _GRADUATE_AT:
        try:
            data = _read_milestones()
            data["owner_graduated"] = True
            _MILESTONES.parent.mkdir(parents=True, exist_ok=True)
            _MILESTONES.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return True
    return False


def clear_graduation() -> None:
    """清除全部對談記憶時一併重置畢業里程碑 → 可重新從嬰兒/一般成長。"""
    try:
        data = _read_milestones()
        if data.pop("owner_graduated", None) is not None:
            _MILESTONES.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def status() -> dict:
    turns = _owner_turns()
    return {
        "running": is_running(),
        "models": {"general": config.MODEL_GENERAL, "code": config.MODEL_CODE},
        "allowlist": len(config.ALLOWLIST_USER_IDS),
        "memory": _memory_counts(),
        "owner_turns": turns,
        "owner_graduated": _owner_graduated(turns),
    }
