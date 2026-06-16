import asyncio
from types import SimpleNamespace

import agent
import bot
import config


class _FakeFile:
    def __init__(self, data):
        self._data = data

    async def download_as_bytearray(self):
        return bytearray(self._data)


class _FakeDoc:
    def __init__(self, data, name):
        self.file_name = name
        self._f = _FakeFile(data)

    async def get_file(self):
        return self._f


def _msg(document=None, photo=None, caption="幫我去背"):
    sent = {}

    async def reply_document(document=None, filename=None, caption=None):
        data = document.getvalue() if hasattr(document, "getvalue") else document
        sent.update(kind="document", filename=filename, data=bytes(data), caption=caption)

    async def reply_text(t):
        sent.update(kind="text", text=t)

    m = SimpleNamespace(text=None, caption=caption, document=document, photo=photo or [],
                        chat=SimpleNamespace(id=1, type="private"), chat_id=1,
                        reply_document=reply_document, reply_text=reply_text)
    return m, sent


def _update_ctx(msg):
    update = SimpleNamespace(effective_message=msg,
                             effective_user=SimpleNamespace(id=777, full_name="J"),
                             effective_chat=msg.chat)

    async def send_chat_action(**k):
        pass

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action))
    return update, ctx


def test_owner_document_triggers_media(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(agent, "handle_media",
                        lambda text, b, name, now: agent.MediaResult(file=b"PNG", filename="x-nobg.png", note="ok"))
    msg, sent = _msg(document=_FakeDoc(b"rawbytes", "x.png"))
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["kind"] == "document" and sent["filename"] == "x-nobg.png"
    assert sent["data"] == b"PNG"


def test_media_text_result_replies_text(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(agent, "handle_media",
                        lambda text, b, name, now: agent.MediaResult(message="做不到"))
    msg, sent = _msg(document=_FakeDoc(b"x", "a.png"))
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["kind"] == "text" and sent["text"] == "做不到"


def test_upload_remembers_image(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    agent.reset()
    monkeypatch.setattr(agent, "handle_media",
                        lambda *a, **k: agent.MediaResult(file=b"OUT", filename="x.pdf", note="ok"))
    msg, sent = _msg(document=_FakeDoc(b"rawbytes", "x.png"), caption="轉pdf")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert agent.has_remembered_media() is True


def test_text_followup_applies_to_remembered_image(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    agent.reset()
    agent.remember_media(b"IMG", "cat.png")
    monkeypatch.setattr(agent, "handle_media_followup",
                        lambda text, now: agent.MediaResult(file=b"PNG", filename="cat-nobg.png", note="去背完成"))
    msg, sent = _msg(caption=None)        # 純文字、無附檔
    msg.text = "幫我去背"
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["kind"] == "document" and sent["filename"] == "cat-nobg.png"


def test_text_media_without_remembered_falls_through(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ACTIONS_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    agent.reset()                          # 沒有記住的圖
    called = {"n": 0}
    monkeypatch.setattr(agent, "handle_media_followup",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or agent.MediaResult(message="x"))
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent = _msg(caption=None)
    msg.text = "幫我去背"
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert called["n"] == 0 and sent["text"] == "一般回覆"


def test_activity_logged(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(config, "ACTIONS_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "好的回覆")
    msg, sent = _msg(caption=None)
    msg.text = "幫我查明天天氣"
    update, ctx = _update_ctx(msg)
    with caplog.at_level(logging.INFO, logger="jayvis"):
        asyncio.run(bot.handle_message(update, ctx))
    log = "\n".join(r.message for r in caplog.records)
    assert "📩" in log and "幫我查明天天氣" in log        # 進站事件 + 預覽
    assert "💬 已回覆" in log                            # 出站結果


def test_blocked_logged(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", set())   # 777 非白名單
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "x")
    msg, sent = _msg(caption=None)
    msg.text = "你好"
    update, ctx = _update_ctx(msg)
    with caplog.at_level(logging.INFO, logger="jayvis"):
        asyncio.run(bot.handle_message(update, ctx))
    log = "\n".join(r.message for r in caplog.records)
    assert "🚫 擋下非白名單" in log


def test_media_disabled_does_not_trigger(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    called = {"n": 0}
    monkeypatch.setattr(agent, "handle_media", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent = _msg(document=_FakeDoc(b"x", "a.png"), caption="")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert called["n"] == 0
