"""LLM 代擬「本週重點」草稿：從近期對話/commits/近期筆記/身份/方向生純文字初稿。唯讀。"""
from datetime import datetime, timedelta

import config
import github_sync
import memory
import persona
from db.connection import get_conn
from llm import generate

_SYSTEM = (
    f"請依提供的素材，幫 {config.OWNER_NAME} 擬一份「本週重點」草稿（純文字／markdown，不要 HTML）。\n"
    "繁體中文、精簡，分兩塊：\n"
    "## 本週在忙什麼\n（依近期對話／commits／筆記／方向歸納）\n"
    "## 交接重點\n（請假時哪件事找誰，可參考團隊/方向）\n"
    "只依素材、不要編造；素材不足的部分從略或寫「（待補）」。這是初稿，使用者會再編修。"
)


def _recent_conversations(now, days=14, limit=8000) -> str:
    start = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    end = now.strftime("%Y-%m-%d %H:%M:%S")
    try:
        rows = memory.conversations_between(start, end)
    except Exception:
        return ""
    if not rows:
        return ""
    text = "\n".join(
        f"[{r['ts']}] {r['person_alias'] or r['person_id']}（{r['kind']}）：{r['content']}" for r in rows)
    return text[:limit]


def _recent_obsidian(top=12) -> str:
    try:
        c = get_conn()
        try:
            rows = c.execute(
                "SELECT raw_text FROM chunks WHERE source_type='obsidian' "
                "AND event_time IS NOT NULL AND event_time != '' "
                "ORDER BY event_time DESC LIMIT :n", {"n": top}).fetchall()
        finally:
            c.close()
        return "\n\n".join(r["raw_text"] for r in rows)
    except Exception:
        return ""


def _profile_context() -> str:
    p = persona.load_profile()
    lines = []
    projs = p.get("projects") or []
    if projs:
        lines.append("專案：" + "、".join(x.get("name", "") for x in projs))
    team = p.get("team") or []
    if team:
        lines.append("團隊：" + "、".join(
            (f"{x.get('name', '')}（{x.get('role', '')}）" if x.get("role") else x.get("name", "")) for x in team))
    return "\n".join(lines)


def draft(brief: str = "", model: str = None, now=None) -> dict:
    now = now or datetime.now()
    model = model or config.MODEL_CODE
    brief = (brief or "").strip()
    convo = _recent_conversations(now)
    status = github_sync.get_project_status()
    notes = _recent_obsidian()
    prof = _profile_context()
    if not convo and not status and not notes and not brief:
        return {"ok": False, "error": "沒有足夠素材可擬（沒有近期對話／commits／筆記／方向），請先給一句方向 🙏"}
    parts = []
    if convo:
        parts.append("## 近期對話（最近兩週）\n" + convo)
    if status:
        parts.append(status)
    if notes:
        parts.append("## 近期筆記\n" + notes)
    if prof:
        parts.append("## 身份/團隊\n" + prof)
    if brief:
        parts.append("## 我的方向\n" + brief)
    draft_text = generate(model=model, system=_SYSTEM,
                          messages=[{"role": "user", "content": "\n\n".join(parts)}], max_output_tokens=1500)
    return {"ok": True, "draft": (draft_text or "").strip()}
