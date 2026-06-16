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


def start() -> None:
    if is_running():
        return
    logf = open(LOG_FILE, "a")
    p = subprocess.Popen([sys.executable, "bot.py"], cwd=str(ROOT),
                         stdout=logf, stderr=subprocess.STDOUT, env=_bot_env())
    PID_FILE.write_text(str(p.pid))


def stop() -> None:
    if PID_FILE.exists():
        try:
            os.kill(int(PID_FILE.read_text().strip()), signal.SIGTERM)
        except Exception:
            pass
        try:
            PID_FILE.unlink()
        except Exception:
            pass


def restart() -> None:
    stop()
    time.sleep(1)
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


def tail_log(n: int = 200, clean: bool = False) -> str:
    if not LOG_FILE.exists():
        return ""
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if clean:
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
