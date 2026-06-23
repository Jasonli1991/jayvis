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
    assert agent.has_remembered_media(1) is True       # _msg 的 chat_id=1


def test_text_followup_applies_to_remembered_image(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    agent.reset()
    agent.remember_media(b"IMG", "cat.png", 1)          # 綁 chat_id=1（與 _msg 一致）
    monkeypatch.setattr(agent, "handle_media_followup",
                        lambda text, now, chat_id: agent.MediaResult(file=b"PNG", filename="cat-nobg.png", note="去背完成"))
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


def _disable_other_gates(monkeypatch):
    monkeypatch.setattr(config, "ACTIONS_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "BROWSE_ENABLED", False)
    monkeypatch.setattr(config, "IMAGE_GEN_ENABLED", False)
    monkeypatch.setattr(config, "CODE_ROOT", "")


def test_photo_with_non_media_caption_goes_to_vision_qa(monkeypatch):
    # 附圖+「問截圖內容」的 caption（非去背/轉檔/調尺寸）→ 不進媒體處理，改走 compose_reply 視覺問答帶圖
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    _disable_other_gates(monkeypatch)
    agent.reset()
    called = {"media": 0}
    monkeypatch.setattr(agent, "handle_media",
                        lambda *a, **k: called.__setitem__("media", called["media"] + 1) or agent.MediaResult(message="x"))
    captured = {}

    def _compose(uid, text, image_bytes=None, *a, **k):
        captured["image"] = image_bytes
        return "看圖回答你"

    monkeypatch.setattr(bot, "compose_reply", _compose)
    msg, sent = _msg(photo=[_FakeDoc(b"IMG", "photo.jpg")],
                     caption="我附圖這個呼叫上線什麼時候會重置呢？")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert called["media"] == 0                       # 沒進媒體處理
    assert captured.get("image") == b"IMG"            # 走視覺問答、帶圖
    assert sent["text"] == "看圖回答你"


def test_photo_with_media_caption_still_triggers_media(monkeypatch):
    # 附圖+真的媒體指令（去背）→ 維持原本媒體處理
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    _disable_other_gates(monkeypatch)
    agent.reset()
    monkeypatch.setattr(agent, "handle_media",
                        lambda text, b, name, now: agent.MediaResult(file=b"PNG", filename="photo-nobg.png", note="ok"))
    msg, sent = _msg(photo=[_FakeDoc(b"IMG", "photo.jpg")], caption="幫我去背")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["kind"] == "document" and sent["filename"] == "photo-nobg.png"


def _raise_quota(*a, **k):
    raise RuntimeError("429 RESOURCE_EXHAUSTED: quota")


def test_compose_quota_error_owner_gets_quota_msg(monkeypatch):
    # owner 問答時模型額度耗盡 → 精準指引（去面板模型路由切 Ollama），不重複 DM 通知自己
    import llm
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    _disable_other_gates(monkeypatch)
    monkeypatch.setattr(bot, "compose_reply", _raise_quota)
    notified = {"n": 0}

    async def _notify(*a, **k):
        notified["n"] += 1

    monkeypatch.setattr(bot, "notify_owner_error", _notify)
    msg, sent = _msg(caption=None)
    msg.text = "今天股價如何"
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["text"] == llm.QUOTA_MSG and notified["n"] == 0


def test_compose_quota_error_colleague_generic_and_notifies(monkeypatch):
    # 同事問答撞額度 → 泛用道歉（「模型路由切 Ollama」對同事沒意義）+ 通知 owner
    import llm
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 999)          # 777 非 owner
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    _disable_other_gates(monkeypatch)
    monkeypatch.setattr(bot, "compose_reply", _raise_quota)
    notified = {"n": 0}

    async def _notify(*a, **k):
        notified["n"] += 1

    monkeypatch.setattr(bot, "notify_owner_error", _notify)
    msg, sent = _msg(caption=None)
    msg.text = "今天股價如何"
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["text"] != llm.QUOTA_MSG and "暫時有點狀況" in sent["text"]
    assert notified["n"] == 1


def test_photo_with_draw_caption_skips_image_gen(monkeypatch):
    # 附圖+「畫」字 caption → 不誤觸生圖（生圖看不到參考圖），改走視覺問答帶圖
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(config, "IMAGE_GEN_ENABLED", True)
    monkeypatch.setattr(config, "ACTIONS_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "BROWSE_ENABLED", False)
    monkeypatch.setattr(config, "CODE_ROOT", "")
    gen = {"n": 0}
    monkeypatch.setattr(bot.image_gen, "craft_prompt",
                        lambda *a, **k: gen.__setitem__("n", gen["n"] + 1) or "p")
    captured = {}

    def _compose(uid, text, image_bytes=None, *a, **k):
        captured["image"] = image_bytes
        return "看圖回答"

    monkeypatch.setattr(bot, "compose_reply", _compose)
    msg, sent = _msg(photo=[_FakeDoc(b"IMG", "photo.jpg")], caption="幫我畫一張類似這樣的")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert gen["n"] == 0                       # 沒進生圖
    assert captured.get("image") == b"IMG"     # 走視覺問答帶圖
