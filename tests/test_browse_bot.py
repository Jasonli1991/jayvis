import asyncio
from types import SimpleNamespace

import pytest
import bot
import config
import browse_agent
import browse_tool


def _msg(text):
    sent = []
    photos = []

    async def reply_text(t, **k):
        sent.append(t)

    async def reply_photo(*a, **k):
        photos.append(1)

    m = SimpleNamespace(text=text, caption=None, document=None, photo=[],
                        chat=SimpleNamespace(id=1, type="private", title=None), chat_id=1,
                        reply_text=reply_text, reply_photo=reply_photo)
    return m, sent, photos


def _update(msg, uid):
    user = SimpleNamespace(id=uid, full_name="U", username="u")
    sent_dms = []

    async def send_message(**k):
        sent_dms.append(k)

    async def send_chat_action(**k):
        pass

    async def send_photo(**k):
        pass

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_message=send_message,
                          send_chat_action=send_chat_action, send_photo=send_photo,
                          sent_dms=sent_dms))
    upd = SimpleNamespace(effective_message=msg, effective_user=user,
                          effective_chat=msg.chat, message=msg)
    return upd, ctx


@pytest.fixture
def _base(monkeypatch):
    monkeypatch.setattr(config, "BROWSE_ENABLED", True)
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "CODE_ROOT", "")          # 關掉 code-delegate gate
    monkeypatch.setattr(config, "ACTIONS_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(bot, "is_owner", lambda uid: uid == 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803, 555})
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {555: "Bob"})
    monkeypatch.setattr(bot, "_cooldown_exempt", lambda u: True)
    monkeypatch.setattr(bot.memory, "append", lambda *a, **k: None)
    bot._pending_browse.clear()


def test_colleague_cannot_browse(monkeypatch, _base):
    called = {"n": 0}
    monkeypatch.setattr(browse_agent, "run", lambda *a, **k: called.__setitem__("n", 1))
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent, _ = _msg("幫我看 https://example.com")
    upd, ctx = _update(msg, 555)              # 同事
    asyncio.run(bot.handle_message(upd, ctx))
    assert called["n"] == 0                    # 同事永遠進不到 browse


def test_owner_read_replies_summary_and_no_memory(monkeypatch, _base):
    monkeypatch.setattr(browse_agent, "run",
                        lambda *a, **k: browse_agent.BrowseResult("ok", summary="流量 12000", screenshot=None))
    appended = []
    monkeypatch.setattr(bot.memory, "append", lambda *a, **k: appended.append(a))
    msg, sent, _ = _msg("幫我看 https://example.com 後台")
    upd, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(upd, ctx))
    assert any("12000" in s for s in sent)
    assert appended == []                      # browse 路徑不入庫


def test_owner_pending_then_confirm(monkeypatch, _base):
    monkeypatch.setattr(browse_agent, "run",
                        lambda *a, **k: browse_agent.BrowseResult("pending", summary="發布", pending={"action": "click", "ref": 3}))
    resumed = {"approved": None}
    monkeypatch.setattr(browse_agent, "resume",
                        lambda pending, approved: resumed.__setitem__("approved", approved)
                        or browse_agent.BrowseResult("ok", summary="已執行"))
    # 第一則：觸發 → pending（需含 URL 或瀏覽關鍵字以觸發 _looks_like_browse）
    msg, sent, _ = _msg("幫我在 https://example.com 把草稿發布")
    upd, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(upd, ctx))
    assert 6803 in bot._pending_browse
    # 第二則：確認 → resume(approved=True)
    msg2, sent2, _ = _msg("確認")
    upd2, ctx2 = _update(msg2, 6803)
    asyncio.run(bot.handle_message(upd2, ctx2))
    assert resumed["approved"] is True
    assert 6803 not in bot._pending_browse


def test_browse_unavailable_message(monkeypatch, _base):
    def _raise(*a, **k):
        raise browse_tool.BrowseUnavailable("no chrome")
    monkeypatch.setattr(browse_agent, "run", _raise)
    msg, sent, _ = _msg("幫我看 https://example.com")
    upd, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(upd, ctx))
    assert any("remote-debugging" in s for s in sent)
