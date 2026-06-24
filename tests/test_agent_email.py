from datetime import datetime

import pytest

import agent
import config
import calendar_tool as cal
import mail_tool as mail


def _now():
    return datetime(2026, 6, 11)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    agent.reset()
    monkeypatch.setattr(cal, "list_calendars", lambda: [])
    monkeypatch.setattr(mail, "list_accounts", lambda: [])     # 不打真 osascript


def test_handle_quota_error_says_quota(monkeypatch):
    def _boom(**k):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: You exceeded your current quota")
    monkeypatch.setattr(agent.llm, "generate", _boom)
    out = agent.handle("寄信給 x@y.com", _now(), email_on=True)
    assert "額度" in out                      # 明確講額度，不是 abstain


def test_handle_truncated_action_not_abstain(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"send_email","to":"a@b.com",')  # 截斷
    out = agent.handle("寄信", _now(), email_on=True)
    assert out is not None and ("不完整" in out or "額度" in out)


def test_handle_non_action_still_none(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: "你好，我是搭檔～")
    assert agent.handle("你好", _now(), email_on=True) is None   # 真非動作 → 交回 bot


def test_handle_model_error_falls_through_to_normal(monkeypatch):
    # 分類階段模型/連線錯誤（非額度，如 500）→ 當作非動作回 None，
    # 交回 bot 走一般 compose_reply（不誤報成 Mail／行事曆沒回應、不丟掉訊息）
    def _boom(**k):
        raise RuntimeError("500 INTERNAL")
    monkeypatch.setattr(agent.llm, "generate", _boom)
    assert agent.handle("寄信", _now(), email_on=True) is None


def test_email_intent_ignored_when_email_off(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"list_email","scope":"unread","n":10}')
    # email_on 預設 False → 視為非動作，交回 bot
    assert agent.handle("有什麼新信", _now()) is None


def test_list_email_immediate(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"list_email","scope":"unread","n":10}')
    monkeypatch.setattr(mail, "list_inbox",
                        lambda scope, n: [{"id": "1", "from": "Sam", "subject": "報告", "date": "d"}])
    out = agent.handle("有什麼未讀信", _now(), email_on=True)
    assert "Sam" in out and "報告" in out


def test_send_asks_account_then_sends(monkeypatch):
    monkeypatch.setattr(config, "MAIL_ACCOUNT", "")
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"send_email","to":"a@b.com","subject":"嗨","body":"內文"}')
    monkeypatch.setattr(mail, "list_accounts", lambda: ["me@x.com", "work@dash.com"])
    sent = {}
    monkeypatch.setattr(mail, "send_mail",
                        lambda to, subject, body, account="": sent.update(to=to, account=account) or {"sent": True})
    out1 = agent.handle("寄信給 a@b.com 說嗨", _now(), email_on=True)
    assert "要用哪個帳號寄" in out1 and "1. me@x.com" in out1
    out2 = agent.handle("2", _now(), email_on=True)            # work@dash.com
    assert "a@b.com" in out2 and "嗨" in out2 and "yes" in out2.lower()
    assert sent == {}                                          # 還沒寄
    out3 = agent.handle("yes", _now(), email_on=True)
    assert sent["to"] == "a@b.com" and sent["account"] == "work@dash.com"
    assert "已寄出" in out3


def test_send_uses_default_account(monkeypatch):
    monkeypatch.setattr(config, "MAIL_ACCOUNT", "me@x.com")
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"send_email","to":"a@b.com","subject":"S","body":"B"}')
    monkeypatch.setattr(mail, "send_mail", lambda **k: {"sent": True})
    out1 = agent.handle("寄信", _now(), email_on=True)
    assert "要用哪個帳號" not in out1 and "yes" in out1.lower()   # 直接確認


def test_send_cancel(monkeypatch):
    monkeypatch.setattr(config, "MAIL_ACCOUNT", "me@x.com")
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"send_email","to":"a@b.com","subject":"S","body":"B"}')
    monkeypatch.setattr(mail, "send_mail", lambda **k: (_ for _ in ()).throw(AssertionError("不該寄")))
    agent.handle("寄信", _now(), email_on=True)
    assert "取消" in agent.handle("不要", _now(), email_on=True)   # 整句＝取消詞 → 取消


def test_send_refine_then_send(monkeypatch):
    monkeypatch.setattr(config, "MAIL_ACCOUNT", "me@x.com")
    gens = []

    def _gen(**k):
        gens.append(k)
        if len(gens) == 1:
            return '{"action":"send_email","to":"a@b.com","subject":"羽球","body":"禮拜六打球"}'
        return '{"to":"a@b.com","subject":"羽球","body":"6/13（週六）打球"}'   # 修改後草稿
    monkeypatch.setattr(agent.llm, "generate", _gen)
    sent = {}
    monkeypatch.setattr(mail, "send_mail",
                        lambda to, subject, body, account="": sent.update(body=body) or {"sent": True})
    out1 = agent.handle("寄信", _now(), email_on=True)
    assert "禮拜六打球" in out1 and "yes" in out1.lower()
    out2 = agent.handle("補上確切日期", _now(), email_on=True)      # 非 yes/取消 → 改草稿
    assert "6/13" in out2 and "yes" in out2.lower()               # 新預覽
    assert sent == {}                                             # 還沒寄
    out3 = agent.handle("yes", _now(), email_on=True)
    assert "6/13" in sent["body"] and "已寄出" in out3


def test_read_single_returns_body(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"read_email","match":{"from":"Sam","subject":""},"summarize":false}')
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [
        {"id": "9", "from": "Sam", "subject": "報告", "date": "d"}])
    monkeypatch.setattr(mail, "read_message",
                        lambda mid: {"from": "Sam", "subject": "報告", "body": "請看附件內容"})
    out = agent.handle("念 Sam 那封給我", _now(), email_on=True)
    assert "報告" in out and "請看附件內容" in out


def test_read_multi_selects(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"read_email","match":{"from":"","subject":"報告"},"summarize":false}')
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [
        {"id": "1", "from": "Sam", "subject": "報告A", "date": "d"},
        {"id": "2", "from": "Jordan", "subject": "報告B", "date": "d"}])
    monkeypatch.setattr(mail, "read_message", lambda mid: {"from": "Jordan", "subject": "報告B", "body": "內容B"})
    out1 = agent.handle("讀報告那封", _now(), email_on=True)
    assert "1." in out1 and "2." in out1 and "哪一封" in out1
    out2 = agent.handle("2", _now(), email_on=True)
    assert "內容B" in out2


def test_read_summarize(monkeypatch):
    calls = []
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: calls.append(k) or (
                            '{"action":"read_email","match":{"from":"Sam","subject":""},"summarize":true}'
                            if len(calls) == 1 else "三句摘要…"))
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [
        {"id": "9", "from": "Sam", "subject": "報告", "date": "d"}])
    monkeypatch.setattr(mail, "read_message",
                        lambda mid: {"from": "Sam", "subject": "報告", "body": "很長的內文"})
    out = agent.handle("摘要 Sam 那封", _now(), email_on=True)
    assert "摘要" in out and "三句摘要" in out


def test_read_no_match(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"read_email","match":{"from":"無此人","subject":""}}')
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [])
    assert "找不到" in agent.handle("讀那封", _now(), email_on=True)
