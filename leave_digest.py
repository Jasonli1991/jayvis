"""請假期間彙整：把同事對話整理成「已處理項目 + 待辦」，供面板顯示與 TG 通知。唯讀、不寫記憶。"""
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import config
import memory
from llm import generate
from panel import env_io

_SENT_MARKER = Path(os.path.expanduser("~/.n/leave_digest_sent.txt"))
_TG_LIMIT = 4000

_DIGEST_SYSTEM = (
    f"以下是 {config.OWNER_NAME} 請假期間，同事與助理的對話紀錄。\n"
    "請彙整成兩塊，繁體中文、條列、標出同事與時間：\n"
    "## 已處理的項目\n（同事問了什麼、助理回覆或處理了什麼）\n"
    f"## 待辦／需 {config.OWNER_NAME} 決定\n（助理說要轉達的、未解決、需本人拍板的事）\n"
    "只根據紀錄、不要編造；某塊沒有就寫「無」。"
)


def compile_digest(model=None, now=None) -> dict:
    """撈請假區間同事對話 → 模型彙整。沒設請假/無紀錄 → fail-fast 不呼叫 LLM。"""
    model = model or config.MODEL_CODE
    leave = env_io.read_leave()
    start, end = leave.get("leave_start"), leave.get("leave_end")
    if not start or not end:
        return {"ok": False, "error": "尚未設定請假期間，請先在請假設定填好日期區間 🙏"}
    rows = memory.conversations_between(start, end + " 23:59:59",
                                        exclude_person_id=str(config.OWNER_CHAT_ID))
    if not rows:
        return {"ok": False, "error": "請假期間沒有同事互動紀錄。"}
    ctx = "\n".join(
        f"[{r['ts']}] {r['person_alias'] or r['person_id']}（{r['kind']}）：{r['content']}" for r in rows)
    summary = generate(model=model, system=_DIGEST_SYSTEM,
                       messages=[{"role": "user", "content": ctx}], max_output_tokens=3000)
    return {"ok": True, "summary": (summary or "").strip()}


def send_to_owner(text: str) -> bool:
    """HTTP 打 Bot API sendMessage 給 owner（超長分段）。token/owner 未設 → False。"""
    token, owner = config.TG_BOT_TOKEN, config.OWNER_CHAT_ID
    if not token or not owner:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = False
    for i in range(0, len(text), _TG_LIMIT):
        data = urllib.parse.urlencode({"chat_id": owner, "text": text[i:i + _TG_LIMIT]}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10):
                ok = True
        except Exception:
            pass
    return ok


def _already_sent(end: str) -> bool:
    try:
        return _SENT_MARKER.read_text(encoding="utf-8").strip() == end
    except Exception:
        return False


def _mark_sent(end: str) -> None:
    try:
        _SENT_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _SENT_MARKER.write_text(end, encoding="utf-8")
    except Exception:
        pass


def check_and_send(now=None) -> bool:
    """bot 背景檢查：請假結束且未發過 → 彙整並 DM owner（一次）。沒設請假 → fail-fast。"""
    now = now or datetime.now()
    leave = env_io.read_leave()
    start, end = leave.get("leave_start"), leave.get("leave_end")
    if not start or not end:
        return False
    try:
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return False
    if now.date() <= end_date:
        return False
    if _already_sent(end):
        return False
    result = compile_digest(now=now)
    if result.get("ok") and result.get("summary"):
        send_to_owner("📋 你請假結束了，這是期間彙整：\n\n" + result["summary"])
    _mark_sent(end)
    return True
