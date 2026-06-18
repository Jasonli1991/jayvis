"""owner 知識問答 → Obsidian vault 的 00_Raw/Inbox 捕捉。路徑由 config.OBSIDIAN_PATH 推導。"""
import logging
import os
import re

import config
from llm import generate

_log = logging.getLogger("jayvis")

INBOX_SUBPATH = ("00_Raw", "Inbox")          # vault 內固定相對結構（不寫死使用者前綴）
SAVE_WORDS = {"存", "存檔", "存起來", "記下來", "記一下", "記到inbox", "記到 inbox", "存進inbox", "yes"}
OFFER_LINE = "\n\n—\n（這題我手邊沒有資料。要我記進 Obsidian Inbox 嗎？回「存」就存）"

_pending = {}    # owner 單格：{"q":..., "a":...}（記憶體、重啟清空）


def remember(question, answer):
    _pending.clear()
    _pending.update(q=question, a=answer)


def has_pending() -> bool:
    return bool(_pending)


def take() -> dict:
    cap = dict(_pending)
    _pending.clear()
    return cap


def clear():
    _pending.clear()


def is_save_command(text) -> bool:
    return (text or "").strip().lower() in SAVE_WORDS


def _slug(text, n=40):
    s = re.sub(r"\s+", "-", (text or "").strip())
    s = re.sub(r"[^\w一-鿿\-]", "", s)
    return (s[:n] or "note").strip("-")


def save_to_inbox(question, answer, now) -> tuple:
    """寫一則 fleeting note 進 vault 的 00_Raw/Inbox。回 (ok, 檔名 or 錯誤訊息)。"""
    root = (config.OBSIDIAN_PATH or "").strip()
    if not root or not os.path.isdir(root):
        return False, "存不進去——Obsidian 路徑沒設好或找不到，先去控制台「記憶重灌」把 vault 路徑填對 🙏"
    inbox = os.path.join(root, *INBOX_SUBPATH)
    try:
        os.makedirs(inbox, exist_ok=True)
        fname = f"{now.strftime('%Y-%m-%d-%H%M')}-{_slug(question)}.md"
        body = ("---\n"
                f"created: {now.strftime('%Y-%m-%dT%H:%M')}\nsource: JAYVIS\ntags: [inbox, fleeting]\n---\n"
                f"# {question.strip()}\n\n（JAYVIS 盡力回答，未經查證）\n{answer.strip()}\n")
        with open(os.path.join(inbox, fname), "w", encoding="utf-8") as f:
            f.write(body)
        return True, fname
    except Exception:
        _log.exception("inbox save failed")
        return False, "存進 Inbox 時出了點狀況（寫檔失敗），等一下再試 🙏"


def is_knowledge_question(text) -> bool:
    """便宜 LLM 判是否知識/學習型問題。失敗/空 → False（不提示）。"""
    t = (text or "").strip()
    if not t:
        return False
    sys = ("判斷這句是不是『值得存進工作知識庫(Obsidian)的知識型問題』——"
           "偏技術／專業／概念／原理／比較／可重用的方法論，日後查得到、用得上的那種。\n"
           "**以下一律不算**：個人身體或健康狀況、生活瑣事、情緒抒發、求助雜事、"
           "閒聊問候感謝、時事天氣、一次性的事。\n"
           "拿不準就回 no（寧可不提示）。只回 yes 或 no。")
    try:
        out = generate(model=config.MODEL_GENERAL, system=sys,
                       messages=[{"role": "user", "content": t[:500]}], max_output_tokens=8)
        return "yes" in (out or "").strip().lower()
    except Exception:
        return False
