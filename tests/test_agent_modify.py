from datetime import datetime

import pytest

import agent
import calendar_tool as cal


def _now():
    return datetime(2026, 6, 11)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    agent.reset()
    monkeypatch.setattr(cal, "list_calendars", lambda: [])   # 不打真 osascript


def _intent(monkeypatch, payload):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: payload)


def test_delete_single_match_confirm_executes(monkeypatch):
    _intent(monkeypatch, '{"action":"delete","match":{"title":"Max","date":"2026-06-15"}}')
    monkeypatch.setattr(cal, "list_events", lambda s, e, calendar=None: [
        {"uid": "U1", "title": "與 Max 開會", "start": "2026-06-15T15:00", "end": "2026-06-15T16:00"}])
    deleted = {}
    monkeypatch.setattr(cal, "delete_event", lambda uid, calendar=None: deleted.update(uid=uid) or {"deleted": True})
    out1 = agent.handle("刪掉 6/15 跟 Max 的會議", _now())
    assert "與 Max 開會" in out1 and "yes" in out1.lower()
    assert deleted == {}
    out2 = agent.handle("yes", _now())
    assert deleted["uid"] == "U1" and "清掉" in out2


def test_update_multi_match_select_then_confirm(monkeypatch):
    _intent(monkeypatch, '{"action":"update","match":{"title":"開會","date":"2026-06-15"},"changes":{"start":"2026-06-18T14:00","end":"2026-06-18T15:00"}}')
    monkeypatch.setattr(cal, "list_events", lambda s, e, calendar=None: [
        {"uid": "U1", "title": "與 Max 開會", "start": "2026-06-15T15:00", "end": "2026-06-15T16:00"},
        {"uid": "U2", "title": "與 Jordan 開會", "start": "2026-06-15T17:00", "end": "2026-06-15T18:00"}])
    updated = {}
    monkeypatch.setattr(cal, "update_event", lambda uid, changes, calendar=None: updated.update(uid=uid, changes=changes) or {"updated": True})
    out1 = agent.handle("把 6/15 的開會改到 18 號下午兩點", _now())
    assert "1." in out1 and "2." in out1 and "哪" in out1     # 請選編號
    out2 = agent.handle("2", _now())                          # 選第二個
    assert "yes" in out2.lower()
    out3 = agent.handle("yes", _now())
    assert updated["uid"] == "U2" and updated["changes"]["start"] == "2026-06-18T14:00"
    assert "更新" in out3


def test_modify_no_match(monkeypatch):
    _intent(monkeypatch, '{"action":"delete","match":{"title":"不存在","date":"2026-06-15"}}')
    monkeypatch.setattr(cal, "list_events", lambda s, e, calendar=None: [])
    out = agent.handle("刪掉那個會", _now())
    assert "找不到" in out
