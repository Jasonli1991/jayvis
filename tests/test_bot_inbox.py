import asyncio
from types import SimpleNamespace

import bot
import config


def _msg(text):
    sent = []

    async def reply_text(t):
        sent.append(t)

    m = SimpleNamespace(text=text, caption=None, document=None, photo=[],
                        chat=SimpleNamespace(id=1, type="private", title=None), chat_id=1,
                        reply_text=reply_text)
    return m, sent


def _update(msg, uid):
    update = SimpleNamespace(effective_message=msg,
                             effective_user=SimpleNamespace(id=uid, full_name="Owner"),
                             effective_chat=msg.chat)

    async def send_chat_action(**k):
        pass

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action))
    return update, ctx


def test_owner_save_command_writes_inbox(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    bot.inbox_capture.clear()
    bot.inbox_capture.remember("ReAct 是什麼？", "ReAct 是…")
    saved = {}
    monkeypatch.setattr(bot.inbox_capture, "save_to_inbox",
                        lambda q, a, now: saved.update(q=q, a=a) or (True, "2026-06-15-1830-ReAct.md"))
    msg, sent = _msg("存")
    update, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(update, ctx))
    assert saved["q"] == "ReAct 是什麼？"
    assert any("已存進" in s for s in sent)
    assert bot.inbox_capture.has_pending() is False    # take 清掉


def test_owner_save_command_no_pending_falls_through(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(config, "ACTIONS_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    bot.inbox_capture.clear()
    called = {"save": 0}
    monkeypatch.setattr(bot.inbox_capture, "save_to_inbox",
                        lambda *a, **k: called.__setitem__("save", 1) or (True, "x"))
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent = _msg("存")
    update, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(update, ctx))
    assert called["save"] == 0                         # 無暫存 → 沒寫檔
    assert any("一般回覆" in s for s in sent)           # 往下走 compose_reply
