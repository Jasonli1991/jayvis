import asyncio
import time
from types import SimpleNamespace

import pytest
import bot
import browse_allowlist
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
    bot._browse_session.clear()


def test_colleague_cannot_browse(monkeypatch, _base):
    called = {"n": 0}
    monkeypatch.setattr(browse_agent, "run", lambda *a, **k: called.__setitem__("n", 1))
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent, _ = _msg("幫我看 https://example.com")
    upd, ctx = _update(msg, 555)              # 同事
    asyncio.run(bot.handle_message(upd, ctx))
    assert called["n"] == 0                    # 同事永遠進不到 browse


def test_browse_precedes_code_delegation(monkeypatch, _base):
    # 回歸：訊息含網域名（ka2ka.com）會撞同名專案；明確「瀏覽」意圖須優先於程式委派，不被攔走。
    monkeypatch.setattr(config, "CODE_ROOT", "/some/code/root")     # 打開 code-delegate gate
    ran = {"browse": 0}
    asked = {"code": 0}
    monkeypatch.setattr(browse_agent, "run",
                        lambda *a, **k: ran.__setitem__("browse", 1)
                        or browse_agent.BrowseResult("ok", summary="ka2ka 首頁看起來…", screenshot=None))
    monkeypatch.setattr(bot.code_delegate, "classify", lambda text: "ka2ka")   # 模擬撞專案名
    monkeypatch.setattr(bot.code_delegate, "ask",
                        lambda *a, **k: asked.__setitem__("code", 1) or "不該被呼叫")
    msg, sent, _ = _msg("可以幫我瀏覽ka2ka.com這個網站嗎？")
    upd, ctx = _update(msg, 6803)              # owner
    asyncio.run(bot.handle_message(upd, ctx))
    assert ran["browse"] == 1                   # 走瀏覽
    assert asked["code"] == 0                   # 沒被程式委派攔走


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


def test_extract_url_and_looks_like_browse():
    assert bot._extract_browse_url("進ka2ka.com這個網站") == "https://ka2ka.com"
    assert bot._extract_browse_url("看 https://a.example.com/x 這頁") == "https://a.example.com/x"
    assert bot._extract_browse_url("今天天氣如何") is None
    assert bot._looks_like_browse("可以幫我進ka2ka.com這個網站截圖首頁") is True   # 裸網域 → 瀏覽
    assert bot._looks_like_browse("今天天氣如何") is False                       # 一般聊天不誤判


def test_browse_passes_detected_url_as_start(monkeypatch, _base):
    got = {}
    monkeypatch.setattr(browse_agent, "run",
                        lambda task, start_url=None, *a, **k: got.update(task=task, start=start_url)
                        or browse_agent.BrowseResult("ok", summary="ok", screenshot=None))
    m, _, _ = _msg("可以幫我進ka2ka.com這個網站截圖首頁")
    u, c = _update(m, 6803)
    asyncio.run(bot.handle_message(u, c))
    assert got["start"] == "https://ka2ka.com"        # 偵測到的網址直接帶去導航


def test_browse_session_routes_followups(monkeypatch, _base):
    # 進入瀏覽後，後續沒有「瀏覽」關鍵字的訊息（截圖/點登入）仍須走瀏覽工具，不掉回一般聊天。
    calls = []
    monkeypatch.setattr(browse_agent, "run",
                        lambda task, *a, **k: calls.append(task)
                        or browse_agent.BrowseResult("ok", summary="ok", screenshot=None))
    compose = []
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: compose.append(1) or "一般回覆")
    m1, _, _ = _msg("幫我瀏覽 ka2ka.com")
    u1, c1 = _update(m1, 6803)
    asyncio.run(bot.handle_message(u1, c1))
    m2, _, _ = _msg("幫我截圖")                 # 無瀏覽關鍵字
    u2, c2 = _update(m2, 6803)
    asyncio.run(bot.handle_message(u2, c2))
    assert calls == ["幫我瀏覽 ka2ka.com", "幫我截圖"]
    assert compose == []                        # 後續沒掉回一般聊天（不會謊稱沒功能）


def test_browse_session_stop_word(monkeypatch, _base):
    bot._browse_session[6803] = time.time()     # 模擬瀏覽模式中
    ran = []
    monkeypatch.setattr(browse_agent, "run", lambda *a, **k: ran.append(1))
    m, sent, _ = _msg("結束瀏覽")
    u, c = _update(m, 6803)
    asyncio.run(bot.handle_message(u, c))
    assert ran == []                            # 停止指令不觸發瀏覽
    assert 6803 not in bot._browse_session       # 已離開瀏覽模式
    assert any("結束瀏覽" in s for s in sent)


def test_browse_unavailable_message(monkeypatch, _base):
    def _raise(*a, **k):
        raise browse_tool.BrowseUnavailable("no chrome")
    monkeypatch.setattr(browse_agent, "run", _raise)
    msg, sent, _ = _msg("幫我看 https://example.com")
    upd, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(upd, ctx))
    assert any("啟用網站瀏覽" in s for s in sent)


def test_pending_confirm_expires(monkeypatch, _base):
    """TTL 過期後送出「確認」不應呼叫 browse_agent.resume"""
    resumed = {"called": False}
    monkeypatch.setattr(browse_agent, "resume",
                        lambda *a, **k: resumed.__setitem__("called", True)
                        or browse_agent.BrowseResult("ok", summary="done"))
    # 直接注入一筆過期的 pending
    bot._pending_browse[6803] = {"pending": {"action": "click"}, "ts": time.time() - 9999}
    msg, sent, _ = _msg("確認")
    upd, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(upd, ctx))
    assert not resumed["called"], "resume 不應被呼叫（pending 已過期）"
    assert 6803 not in bot._pending_browse
    assert any("過期" in s or "逾時" in s for s in sent)


def test_add_whitelist_command(monkeypatch, _base):
    """owner 送「加白名單 example.com」應呼叫 browse_allowlist.add 並回覆確認"""
    added = []
    monkeypatch.setattr(browse_allowlist, "add", lambda domain: added.append(domain))
    msg, sent, _ = _msg("加白名單 example.com")
    upd, ctx = _update(msg, 6803)
    asyncio.run(bot.handle_message(upd, ctx))
    assert added == ["example.com"], "browse_allowlist.add 應以 'example.com' 呼叫"
    assert any("example.com" in s for s in sent)
