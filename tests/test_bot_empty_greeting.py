"""只 @ bot／空訊息時的招呼語：依實際請假狀態，沒請假就不該說「請假中」。"""
import asyncio
from types import SimpleNamespace

import bot
import config


def _msg(text=None):
    sent = {}

    async def reply_text(t): sent.update(text=t)

    m = SimpleNamespace(text=text, caption=None, document=None, photo=[],
                        chat=SimpleNamespace(id=1, type="private", title=None), chat_id=1,
                        reply_text=reply_text)
    return m, sent


def _ctx_update(msg, uid=6803):
    update = SimpleNamespace(effective_message=msg,
                             effective_user=SimpleNamespace(id=uid, full_name="Owner"),
                             effective_chat=msg.chat)

    async def send_chat_action(**k): pass

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action))
    return update, ctx


def test_empty_message_not_on_leave_no_leave_claim(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(bot.env_io, "is_on_leave", lambda: False)
    msg, sent = _msg(text=None)
    update, ctx = _ctx_update(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert "請假" not in sent["text"]                 # 沒設請假就不該宣稱請假中
    assert config.OWNER_NAME in sent["text"]


def test_empty_message_on_leave_says_leave(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(bot.env_io, "is_on_leave", lambda: True)
    msg, sent = _msg(text=None)
    update, ctx = _ctx_update(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert "請假中" in sent["text"]                    # 真的在請假才說請假中
