"""群組裡 owner 本人可用生圖／媒體工具（被 @ 才觸發）；同事與瀏覽維持原樣。"""
import asyncio
from types import SimpleNamespace

import agent
import bot
import config
import memory


class _FakeFile:
    def __init__(self, data): self._data = data
    async def download_as_bytearray(self): return bytearray(self._data)


class _FakeDoc:
    def __init__(self, data, name):
        self.file_name = name
        self._f = _FakeFile(data)
    async def get_file(self): return self._f


def _group_msg(text=None, caption=None, document=None, photo=None):
    sent = {}

    async def reply_text(t): sent.update(kind="text", text=t)

    async def reply_document(document=None, filename=None, caption=None):
        data = document.getvalue() if hasattr(document, "getvalue") else document
        sent.update(kind="document", filename=filename, data=bytes(data), caption=caption)

    m = SimpleNamespace(text=text, caption=caption, document=document, photo=photo or [],
                        chat=SimpleNamespace(id=9, type="supergroup", title="Team"), chat_id=9,
                        reply_text=reply_text, reply_document=reply_document)
    return m, sent


def _update_ctx(msg, sent, uid=777):
    update = SimpleNamespace(effective_message=msg,
                             effective_user=SimpleNamespace(id=uid, full_name="Owner"),
                             effective_chat=msg.chat)

    async def send_chat_action(**k): pass

    async def send_photo(chat_id=None, photo=None):
        data = photo.getvalue() if hasattr(photo, "getvalue") else photo
        sent.setdefault("photos", []).append(bytes(data))

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action,
                                              send_photo=send_photo))
    return update, ctx


def test_owner_group_document_routes_media(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "MEDIA_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(agent, "handle_media",
                        lambda text, b, name, now: agent.MediaResult(file=b"PNG", filename="x-nobg.png", note="ok"))
    msg, sent = _group_msg(caption="@bot 幫我去背", document=_FakeDoc(b"raw", "x.png"))
    update, ctx = _update_ctx(msg, sent)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent.get("kind") == "document" and sent["filename"] == "x-nobg.png"
    assert memory.recent(777) == []        # 群組媒體不污染 owner 私訊線性記憶（not is_group 防護）


def test_owner_group_image_request_routes_image_gen(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "IMAGE_GEN_ENABLED", True)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(bot, "_recent_context", lambda uid, n=4: "")
    monkeypatch.setattr(bot.image_gen, "craft_prompt", lambda text, ctx="": "a cat")
    gen = []
    monkeypatch.setattr(bot.image_gen, "generate", lambda p: gen.append(p) or b"PNGIMG")
    msg, sent = _group_msg(text="@bot 幫我畫一隻貓")
    update, ctx = _update_ctx(msg, sent)
    asyncio.run(bot.handle_message(update, ctx))
    assert gen == ["a cat"] and sent.get("photos") == [b"PNGIMG"]


def test_colleague_group_image_request_not_routed(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "IMAGE_GEN_ENABLED", True)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {555})     # 同事在白名單、但非 owner
    gen = []
    monkeypatch.setattr(bot.image_gen, "generate", lambda p: gen.append(p) or b"X")
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "同事模式回覆")
    msg, sent = _group_msg(text="@bot 幫我畫一隻貓")
    update, ctx = _update_ctx(msg, sent, uid=555)
    asyncio.run(bot.handle_message(update, ctx))
    assert gen == [] and sent.get("text") == "同事模式回覆"


def test_browse_in_group_still_not_routed(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "BROWSE_ENABLED", True)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(config, "IMAGE_GEN_ENABLED", False)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    ran = {"n": 0}

    async def fake_run_browse(*a, **k): ran["n"] += 1

    monkeypatch.setattr(bot, "_run_browse", fake_run_browse)
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "同事模式回覆")
    msg, sent = _group_msg(text="@bot 幫我看 https://example.com")
    update, ctx = _update_ctx(msg, sent)
    asyncio.run(bot.handle_message(update, ctx))
    assert ran["n"] == 0 and sent.get("text") == "同事模式回覆"      # 瀏覽在群組仍不觸發
