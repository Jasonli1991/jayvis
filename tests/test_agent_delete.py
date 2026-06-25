from datetime import datetime

import pytest

import agent
import calendar_tool as cal
import mail_tool as mail


def _now():
    return datetime(2026, 6, 11)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    agent.reset()
    monkeypatch.setattr(cal, "list_calendars", lambda: [])
    monkeypatch.setattr(mail, "list_accounts", lambda: [])


def _list_then(monkeypatch, intent_after):
    """先列信（填 _last_list），再讓下一次 generate 回 intent_after。"""
    calls = []
    inbox = [{"id": "11", "from": "Sam", "subject": "報告", "date": "d"},
             {"id": "22", "from": "Discord", "subject": "提到您", "date": "d"}]
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: inbox)

    def _gen(**k):
        calls.append(1)
        return ('{"action":"list_email","scope":"unread","n":10}' if len(calls) == 1 else intent_after)
    monkeypatch.setattr(agent.llm, "generate", _gen)


def test_list_email_fills_last_list(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"list_email","scope":"unread","n":10}')
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [
        {"id": "11", "from": "Sam", "subject": "報告", "date": "d"}])
    agent.handle("列信", _now(), email_on=True)
    assert agent._last_list and agent._last_list[0]["id"] == "11"


def test_delete_by_ref_confirms_then_deletes(monkeypatch):
    _list_then(monkeypatch, '{"action":"delete_email","ref":2}')
    deleted = {}
    monkeypatch.setattr(mail, "delete_message", lambda mid: deleted.update(id=mid) or {"deleted": True})
    agent.handle("列信", _now(), email_on=True)               # 填 _last_list
    out1 = agent.handle("把2刪除", _now(), email_on=True)
    assert "Discord" in out1 and "yes" in out1.lower() and "垃圾桶" in out1
    assert deleted == {}                                       # 還沒刪
    out2 = agent.handle("yes", _now(), email_on=True)
    assert deleted["id"] == "22" and "刪掉" in out2


def test_delete_ref_without_list(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"delete_email","ref":2}')
    out = agent.handle("刪第2封", _now(), email_on=True)
    assert "先列信" in out


def test_delete_ref_out_of_range(monkeypatch):
    _list_then(monkeypatch, '{"action":"delete_email","ref":9}')
    agent.handle("列信", _now(), email_on=True)
    out = agent.handle("刪第9封", _now(), email_on=True)
    assert "沒有第 9 封" in out


def test_delete_by_match_single(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"delete_email","match":{"from":"Discord","subject":""}}')
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [
        {"id": "22", "from": "Discord", "subject": "提到您", "date": "d"}])
    deleted = {}
    monkeypatch.setattr(mail, "delete_message", lambda mid: deleted.update(id=mid) or {"deleted": True})
    out1 = agent.handle("刪除 Discord 那封", _now(), email_on=True)
    assert "Discord" in out1 and "yes" in out1.lower()
    out2 = agent.handle("yes", _now(), email_on=True)
    assert deleted["id"] == "22"


def test_delete_by_match_multi_selects(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"delete_email","match":{"from":"","subject":"通知"}}')
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [
        {"id": "1", "from": "A", "subject": "通知一", "date": "d"},
        {"id": "2", "from": "B", "subject": "通知二", "date": "d"}])
    deleted = {}
    monkeypatch.setattr(mail, "delete_message", lambda mid: deleted.update(id=mid) or {"deleted": True})
    out1 = agent.handle("刪掉通知那封", _now(), email_on=True)
    assert "1." in out1 and "2." in out1 and "刪哪一封" in out1
    out2 = agent.handle("2", _now(), email_on=True)
    assert "yes" in out2.lower() and "B" in out2
    out3 = agent.handle("yes", _now(), email_on=True)
    assert deleted["id"] == "2" and "刪掉" in out3


def test_read_by_ref(monkeypatch):
    _list_then(monkeypatch, '{"action":"read_email","ref":2,"summarize":false}')
    monkeypatch.setattr(mail, "read_message",
                        lambda mid: {"from": "Discord", "subject": "提到您", "body": "內容X"})
    agent.handle("列信", _now(), email_on=True)               # 填 _last_list（第2封 id=22）
    out = agent.handle("讀第2封", _now(), email_on=True)
    assert "提到您" in out and "內容X" in out


def test_read_ref_without_list(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"read_email","ref":2}')
    out = agent.handle("讀第2封", _now(), email_on=True)
    assert "先列信" in out


def test_read_still_works_after_op_change(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"read_email","match":{"from":"","subject":"報告"},"summarize":false}')
    monkeypatch.setattr(mail, "list_inbox", lambda scope, n: [
        {"id": "1", "from": "Sam", "subject": "報告A", "date": "d"},
        {"id": "2", "from": "Jordan", "subject": "報告B", "date": "d"}])
    monkeypatch.setattr(mail, "read_message", lambda mid: {"from": "Jordan", "subject": "報告B", "body": "內容B"})
    agent.handle("讀報告那封", _now(), email_on=True)
    out = agent.handle("2", _now(), email_on=True)
    assert "內容B" in out                         # op=read 路徑不回歸
