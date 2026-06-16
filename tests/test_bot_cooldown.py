from types import SimpleNamespace

import bot
import config


def _user(uid, name="Bob"):
    return SimpleNamespace(id=uid, full_name=name)


def test_exempt_owner(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    assert bot._cooldown_exempt(_user(6803, "Owner")) is True


def test_exempt_boss_by_alias(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {321: "BigBoss"})
    monkeypatch.setattr(bot.persona, "load_profile",
                        lambda: {"bosses": [{"name": "BigBoss", "note": ""}]})
    assert bot._cooldown_exempt(_user(321, "BigBoss")) is True


def test_plain_colleague_not_exempt(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {555: "Bob"})
    monkeypatch.setattr(bot.persona, "load_profile",
                        lambda: {"bosses": [{"name": "BigBoss"}]})
    assert bot._cooldown_exempt(_user(555, "Bob")) is False


def test_boss_name_no_matching_alias_not_exempt(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {})      # 沒有別名可對應
    monkeypatch.setattr(bot.persona, "load_profile",
                        lambda: {"bosses": [{"name": "BigBoss"}]})
    assert bot._cooldown_exempt(_user(999, "")) is False


import asyncio

import cooldown


def _msg(text, ctype="private"):
    sent = []

    async def reply_text(t):
        sent.append(t)

    m = SimpleNamespace(text=text, caption=None, document=None, photo=[],
                        chat=SimpleNamespace(id=1, type=ctype, title=None), chat_id=1,
                        reply_text=reply_text)
    return m, sent


def _update(msg, uid, name="Bob"):
    update = SimpleNamespace(effective_message=msg,
                             effective_user=SimpleNamespace(id=uid, full_name=name),
                             effective_chat=msg.chat)

    async def send_chat_action(**k):
        pass

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action))
    return update, ctx


def _colleague_env(monkeypatch, uid=555, alias="Bob"):
    cooldown.reset()
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {uid})
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {uid: alias})
    monkeypatch.setattr(bot.persona, "load_profile", lambda: {"bosses": []})


def test_colleague_locked_after_6_low_priority(monkeypatch):
    _colleague_env(monkeypatch)
    monkeypatch.setattr(bot.cooldown, "looks_low_priority", lambda texts: True)
    calls = {"n": 0}
    monkeypatch.setattr(bot, "compose_reply",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or "回覆")
    last_sent = []
    for i in range(6):
        msg, sent = _msg(f"閒聊{i}")
        update, ctx = _update(msg, 555)
        asyncio.run(bot.handle_message(update, ctx))
        last_sent = sent
    assert calls["n"] == 5                          # 前 5 則照常回，第 6 則被攔
    assert any("先忙" in s for s in last_sent)       # 第 6 則回「先忙」

    msg, sent = _msg("再吵")                          # 第 7 則：鎖定中
    update, ctx = _update(msg, 555)
    asyncio.run(bot.handle_message(update, ctx))
    assert calls["n"] == 5                           # 沒再呼叫 compose_reply
    assert sent == []                                # 靜默


def test_serious_high_freq_not_locked(monkeypatch):
    _colleague_env(monkeypatch)
    monkeypatch.setattr(bot.cooldown, "looks_low_priority", lambda texts: False)
    calls = {"n": 0}
    monkeypatch.setattr(bot, "compose_reply",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or "回覆")
    sent_all = []
    for i in range(8):
        msg, sent = _msg(f"正事{i}")
        update, ctx = _update(msg, 555)
        asyncio.run(bot.handle_message(update, ctx))
        sent_all += sent
    assert calls["n"] == 8                           # 全部照常回
    assert not any("先忙" in s for s in sent_all)     # 未鎖


def test_boss_exempt_never_locked(monkeypatch):
    _colleague_env(monkeypatch, uid=777, alias="BigBoss")
    monkeypatch.setattr(bot.persona, "load_profile",
                        lambda: {"bosses": [{"name": "BigBoss"}]})
    monkeypatch.setattr(bot.cooldown, "looks_low_priority", lambda texts: True)
    calls = {"n": 0}
    monkeypatch.setattr(bot, "compose_reply",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or "回覆")
    sent_all = []
    for i in range(8):
        msg, sent = _msg(f"哈拉{i}")
        update, ctx = _update(msg, 777, name="BigBoss")
        asyncio.run(bot.handle_message(update, ctx))
        sent_all += sent
    assert calls["n"] == 8                           # 老闆豁免 → 全部照常回
    assert not any("先忙" in s for s in sent_all)
