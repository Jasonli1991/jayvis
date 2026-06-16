from datetime import datetime

import pytest

import agent
import config
import calendar_tool as cal


def _now():
    return datetime(2026, 6, 11)


@pytest.fixture(autouse=True)
def _no_real_calendars(monkeypatch):
    agent.reset()
    monkeypatch.setattr(cal, "list_calendars", lambda: [])   # 不打真 osascript（個別測試可覆寫）


def test_action_blocked_on_non_macos(monkeypatch):
    """非 macOS 偵測到行事曆動作 → 回清楚訊息，不去碰 osascript。"""
    monkeypatch.setattr(agent, "IS_MACOS", False)
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"list","start":"2026-06-11T00:00","end":"2026-06-12T00:00"}')
    out = agent.handle("我今天有什麼行程", _now())
    assert "macOS" in out


def test_non_action_still_none_on_non_macos(monkeypatch):
    monkeypatch.setattr(agent, "IS_MACOS", False)
    monkeypatch.setattr(agent.llm, "generate", lambda **k: "你好～")
    assert agent.handle("你好", _now()) is None      # 非動作照常交回 bot


def test_build_system_injects_calendars():
    s = agent.build_system(_now(), ["居家", "工作"])
    assert "可用日曆" in s and "工作" in s
    assert '"calendar"' in s                 # create schema 含 calendar 欄


def test_create_with_explicit_calendar(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "")
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"create","title":"開會","start":"2026-06-12T10:00","end":"2026-06-12T11:00","notes":"","calendar":"工作"}')
    got = {}
    monkeypatch.setattr(cal, "create_event",
                        lambda title, start, end, notes="", calendar=None, all_day=False: got.update(calendar=calendar) or {"uid": "X"})
    out1 = agent.handle("加到工作曆 6/12 早上十點開會", _now())
    assert "【工作】" in out1
    agent.handle("yes", _now())
    assert got["calendar"] == "工作"


def test_create_no_calendar_asks_then_picks(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "")              # 沒設預設
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"create","title":"開會","start":"2026-06-12T10:00","end":"2026-06-12T11:00","notes":""}')
    monkeypatch.setattr(cal, "list_calendars", lambda: ["居家", "工作", "行事曆"])
    got = {}
    monkeypatch.setattr(cal, "create_event",
                        lambda title, start, end, notes="", calendar=None, all_day=False: got.update(calendar=calendar) or {"uid": "X"})
    out1 = agent.handle("幫我約 6/12 早上十點開會", _now())
    assert "哪一本" in out1 and "1. 居家" in out1 and "2. 工作" in out1
    out2 = agent.handle("2", _now())                             # 選工作
    assert "【工作】" in out2 and "yes" in out2.lower()
    agent.handle("yes", _now())
    assert got["calendar"] == "工作"


def test_create_uses_default_calendar_no_ask(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "工作")          # 有設預設
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"create","title":"開會","start":"2026-06-12T10:00","end":"2026-06-12T11:00","notes":""}')
    monkeypatch.setattr(cal, "create_event", lambda title, start, end, notes="", calendar=None, all_day=False: {"uid": "X"})
    out1 = agent.handle("約個會 6/12 早上十點", _now())
    assert "【工作】" in out1                                      # 直接用預設
    assert "哪一本" not in out1                                   # 不反問日曆
