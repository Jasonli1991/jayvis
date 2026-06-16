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


def _update(msg, uid, name="Bob"):
    update = SimpleNamespace(effective_message=msg,
                             effective_user=SimpleNamespace(id=uid, full_name=name),
                             effective_chat=msg.chat)
    sent_dms = []

    async def send_chat_action(**k):
        pass

    async def send_message(chat_id, text):
        sent_dms.append((chat_id, text))

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action,
                                              send_message=send_message, sent_dms=sent_dms))
    return update, ctx


def _base(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "CODE_ROOT", "/some/root")
    monkeypatch.setattr(config, "ACTIONS_ENABLED", False)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(bot.memory, "append", lambda *a, **k: None)


def test_owner_code_question_delegates(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: "projx")
    monkeypatch.setattr(bot.code_delegate, "ask", lambda p, q, now=None: "委派答案")
    called = {"n": 0}
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: called.__setitem__("n", 1) or "一般")
    msg, sent = _msg("projx 為什麼一直 401")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any("Agent" in s for s in sent)                # ack
    assert any("委派答案" in s for s in sent)
    assert called["n"] == 0                                # 沒走一般 compose_reply


def test_classify_none_falls_through(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: None)
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent = _msg("今天天氣")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any("一般回覆" in s for s in sent)


def test_colleague_not_on_leave_no_delegate(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {555})
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {555: "Bob"})
    monkeypatch.setattr(bot.persona, "load_profile", lambda: {"bosses": []})
    monkeypatch.setattr(bot.env_io, "is_on_leave", lambda: False)
    classified = {"n": 0}
    monkeypatch.setattr(bot.code_delegate, "classify",
                        lambda t: classified.__setitem__("n", classified["n"] + 1) or "projx")
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent = _msg("projx 為什麼 401")
    update, ctx = _update(msg, 555)
    asyncio.run(bot.handle_message(update, ctx))
    assert classified["n"] == 0                            # owner 在崗 → 連 classify 都不跑
    assert any("一般回覆" in s for s in sent)


def test_colleague_on_leave_delegates(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {555})
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {555: "Bob"})
    monkeypatch.setattr(bot.persona, "load_profile", lambda: {"bosses": []})
    monkeypatch.setattr(bot.env_io, "is_on_leave", lambda: True)
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: "projx")
    monkeypatch.setattr(bot.code_delegate, "ask", lambda p, q, now=None: "委派答案")
    msg, sent = _msg("projx 為什麼 401")
    update, ctx = _update(msg, 555)
    asyncio.run(bot.handle_message(update, ctx))
    assert any("委派答案" in s for s in sent)


def test_phase_a_answer_appends_fix_offer(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    bot.code_delegate.reset_fix()
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: "projx")
    monkeypatch.setattr(bot.code_delegate, "ask", lambda p, q, now=None: "答案")
    msg, sent = _msg("projx 為什麼 401")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any("修復計畫" in s for s in sent)              # 答完附 offer
    assert bot.code_delegate.has_fix(6803) is True         # 暫存了


def test_owner_fix_command_replies_plan(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    bot.code_delegate.reset_fix()
    bot.code_delegate.remember_fix(6803, "projx", "登入 401")
    monkeypatch.setattr(bot.code_delegate, "plan", lambda p, q, now=None: "修復計畫內容")
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: None)
    msg, sent = _msg("修復計畫")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any("修復計畫內容" in s for s in sent)          # owner 本人直接看
    assert ctx.bot.sent_dms == []                          # 不另外送 DM


def test_colleague_fix_command_sends_to_owner(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {555})
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {555: "Bob"})
    monkeypatch.setattr(bot.persona, "load_profile", lambda: {"bosses": []})
    monkeypatch.setattr(bot.env_io, "is_on_leave", lambda: True)
    bot.code_delegate.reset_fix()
    bot.code_delegate.remember_fix(555, "projx", "登入 401")
    monkeypatch.setattr(bot.code_delegate, "plan", lambda p, q, now=None: "修復計畫內容")
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: None)
    msg, sent = _msg("修復計畫")
    update, ctx = _update(msg, 555)
    asyncio.run(bot.handle_message(update, ctx))
    assert any(cid == 6803 and "修復計畫內容" in txt for cid, txt in ctx.bot.sent_dms)   # 送 owner
    assert any("轉給" in s for s in sent)                  # 同事只收 ack


def test_no_pending_fix_command_falls_through(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    bot.code_delegate.reset_fix()
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: None)
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent = _msg("修復計畫")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any("一般回覆" in s for s in sent)              # 無暫存 → 不攔截


# ── Phase C1 ────────────────────────────────────────────────────────────────
def test_format_apply_report_success():
    res = {"ok": True, "clean": True, "pr_url": "https://github.com/o/r/pull/7",
           "tests": "pass", "alarm": None, "warn": None, "summary": ""}
    out = bot._format_apply_report("projx", "登入 401", res)
    assert "已開 PR" in out and "pull/7" in out and "測試全過" in out


def test_format_apply_report_no_tests():
    res = {"ok": True, "clean": True, "pr_url": "u", "tests": "none",
           "alarm": None, "warn": None, "summary": ""}
    assert "未經自動驗證" in bot._format_apply_report("projx", "q", res)


def test_format_apply_report_tests_unknown():
    res = {"ok": True, "clean": False, "pr_url": "u", "tests": None,
           "alarm": None, "warn": "PR 可能不完整", "summary": ""}
    out = bot._format_apply_report("projx", "q", res)
    assert "測試狀態不明" in out and "PR 可能不完整" in out


def test_format_apply_report_failure_with_alarm():
    res = {"ok": False, "clean": False, "error": "Agent 沒開成 PR",
           "pr_url": None, "tests": None, "alarm": "🚨 動到 main", "summary": "末段輸出"}
    out = bot._format_apply_report("projx", "q", res)
    assert "沒完成" in out and "🚨" in out and "末段輸出" in out


def test_owner_apply_command_runs(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(config, "OWNER_NAME", "Owner")
    cd_mod = bot.code_delegate
    cd_mod.reset_apply()
    cd_mod.remember_apply(6803, "projx", "登入 401", "計畫", origin_chat=None)
    monkeypatch.setattr(cd_mod, "apply",
                        lambda p, q, plan, now=None: {"ok": True, "clean": True,
                        "pr_url": "https://github.com/o/r/pull/7", "tests": "pass",
                        "alarm": None, "warn": None, "summary": ""})
    msg, sent = _msg("執行")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any("pull/7" in s for s in sent)
    assert ctx.bot.sent_dms == []                          # owner 自己觸發 → 不送同事


def test_colleague_apply_clean_notifies(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(config, "OWNER_NAME", "Owner")
    cd_mod = bot.code_delegate
    cd_mod.reset_apply()
    cd_mod.remember_apply(6803, "projx", "q", "計畫", origin_chat=999)   # 同事 chat 999
    monkeypatch.setattr(cd_mod, "apply",
                        lambda p, q, plan, now=None: {"ok": True, "clean": True,
                        "pr_url": "u", "tests": "pass", "alarm": None, "warn": None, "summary": ""})
    msg, sent = _msg("執行")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any(cid == 999 and "已著手處理" in t for cid, t in ctx.bot.sent_dms)


def test_colleague_apply_unclean_says_in_progress(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    monkeypatch.setattr(config, "OWNER_NAME", "Owner")
    cd_mod = bot.code_delegate
    cd_mod.reset_apply()
    cd_mod.remember_apply(6803, "projx", "q", "計畫", origin_chat=999)
    monkeypatch.setattr(cd_mod, "apply",
                        lambda p, q, plan, now=None: {"ok": False, "clean": False,
                        "error": "沒開成 PR", "pr_url": None, "tests": None,
                        "alarm": None, "warn": None, "summary": ""})
    msg, sent = _msg("執行")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    notes = [t for cid, t in ctx.bot.sent_dms if cid == 999]
    assert notes and "還在處理中" in notes[0]
    assert all("pull" not in t and "http" not in t for t in notes)     # 不洩連結


def test_apply_command_no_pending_falls_through(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    bot.code_delegate.reset_apply()
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: None)
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般回覆")
    msg, sent = _msg("執行")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert any("一般回覆" in s for s in sent)


def test_phase_b_records_apply_owner(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {6803})
    bot.code_delegate.reset_apply()
    bot.code_delegate.remember_fix(6803, "projx", "登入 401")
    monkeypatch.setattr(bot.code_delegate, "plan", lambda p, q, now=None: "計畫內容")
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: None)
    msg, sent = _msg("修復計畫")
    update, ctx = _update(msg, 6803, "Owner")
    asyncio.run(bot.handle_message(update, ctx))
    assert bot.code_delegate.has_apply(config.OWNER_CHAT_ID) is True
    assert bot.code_delegate.take_apply(config.OWNER_CHAT_ID)[3] is None   # owner→origin None


def test_phase_b_records_apply_colleague(monkeypatch):
    _base(monkeypatch)
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {555})
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {555: "Bob"})
    monkeypatch.setattr(bot.persona, "load_profile", lambda: {"bosses": []})
    monkeypatch.setattr(bot.env_io, "is_on_leave", lambda: True)
    bot.code_delegate.reset_apply()
    bot.code_delegate.remember_fix(555, "projx", "登入 401")
    monkeypatch.setattr(bot.code_delegate, "plan", lambda p, q, now=None: "計畫內容")
    monkeypatch.setattr(bot.code_delegate, "classify", lambda t: None)
    msg, sent = _msg("修復計畫")
    update, ctx = _update(msg, 555)
    asyncio.run(bot.handle_message(update, ctx))
    assert bot.code_delegate.take_apply(config.OWNER_CHAT_ID)[3] == 1     # 同事 chat_id（fixture=1）


def test_on_error_network_is_quiet(caplog):
    import logging
    from telegram.error import NetworkError
    ctx = SimpleNamespace(error=NetworkError("boom"))
    with caplog.at_level(logging.WARNING):
        asyncio.run(bot.on_error(None, ctx))
    assert any("連線暫斷" in r.message for r in caplog.records)
    assert not any(r.levelname == "ERROR" for r in caplog.records)   # 網路暫斷不該是 ERROR 堆疊


def test_on_error_other_is_error(caplog):
    import logging
    ctx = SimpleNamespace(error=ValueError("real bug"))
    with caplog.at_level(logging.WARNING):
        asyncio.run(bot.on_error(None, ctx))
    assert any(r.levelname == "ERROR" for r in caplog.records)       # 真正的例外才印 ERROR
