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


def _ctx_update(msg, uid=6803):
    update = SimpleNamespace(effective_message=msg,
                             effective_user=SimpleNamespace(id=uid, full_name="Owner"),
                             effective_chat=msg.chat)

    async def send_chat_action(**k):
        pass

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action))
    return update, ctx


def test_format_analysis():
    out = bot._format_analysis({"answer": "結論內容", "sources": ["筆記 a.md", "commit 1234"]})
    assert "結論內容" in out and "依據" in out and "筆記 a.md" in out


def test_send_long_splits():
    msg, sent = _msg("")
    asyncio.run(bot._send_long(msg, "x" * 8000, limit=3500))
    assert len(sent) == 3                       # 8000 / 3500 → 3 則
    assert "".join(sent) == "x" * 8000


def test_owner_analysis_prefix_routes(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    seen = {}
    monkeypatch.setattr(bot.analysis, "analyze",
                        lambda q: seen.update(q=q) or {"answer": "分析結果", "sources": ["s1"]})
    msg, sent = _msg("分析：從初期到現在做貢獻度分析")
    update, ctx = _ctx_update(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert seen["q"] == "從初期到現在做貢獻度分析"      # 前綴被剝掉
    assert any("分析結果" in s for s in sent)


def test_group_analysis_not_routed(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    called = {"n": 0}
    monkeypatch.setattr(bot.analysis, "analyze",
                        lambda q: called.__setitem__("n", 1) or {"answer": "", "sources": []})
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般群組回覆")
    msg, sent = _msg("@bot 分析：機密")
    msg.chat = SimpleNamespace(id=1, type="supergroup", title="Team Group")
    update, ctx = _ctx_update(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert called["n"] == 0                      # 群組不走深度分析
