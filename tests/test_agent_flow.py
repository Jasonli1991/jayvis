from datetime import datetime

import pytest

import agent
import config
import calendar_tool as cal


def _now():
    return datetime(2026, 6, 11)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    agent.reset()                       # 清 pending + 日曆快取（測試隔離）
    monkeypatch.setattr(cal, "list_calendars", lambda: [])   # 不打真 osascript


def test_non_action_returns_none(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: "你好，我是搭檔～")
    assert agent.handle("你是誰", _now()) is None      # 交回 bot 走 RAG


def test_list_executes_immediately(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"list","start":"2026-06-11T00:00","end":"2026-06-12T00:00"}')
    monkeypatch.setattr(cal, "list_events",
                        lambda s, e, calendar=None: [{"uid": "U1", "title": "午餐",
                                                      "start": "2026-06-11T12:00", "end": "2026-06-11T13:00"}])
    out = agent.handle("今天有什麼行程", _now())
    assert "午餐" in out and "12:00" in out


def test_create_needs_confirmation_then_executes(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "Home")       # 有預設曆 → 不問日曆
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"create","title":"與 Max 開會","start":"2026-06-15T15:00","end":"2026-06-15T16:00","notes":""}')
    created = {}
    monkeypatch.setattr(cal, "create_event",
                        lambda title, start, end, notes="", calendar=None, all_day=False: created.update(title=title) or {"uid": "NEW"})
    out1 = agent.handle("幫我約 6/15 下午三點跟 Max 開會", _now())
    assert "與 Max 開會" in out1 and "yes" in out1.lower()
    assert created == {}                              # 還沒執行
    out2 = agent.handle("yes", _now())
    assert created["title"] == "與 Max 開會"
    assert "已新增" in out2


def test_create_cancel(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "Home")       # 有預設曆 → 不問日曆
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"create","title":"X","start":"2026-06-15T15:00","end":"2026-06-15T16:00","notes":""}')
    monkeypatch.setattr(cal, "create_event", lambda **k: (_ for _ in ()).throw(AssertionError("不該執行")))
    agent.handle("約個會", _now())
    out = agent.handle("不要", _now())
    assert "取消" in out
