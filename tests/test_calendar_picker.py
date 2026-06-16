from datetime import datetime

import pytest

import agent
import config
import calendar_tool as cal


def _now():
    return datetime(2026, 6, 11)


def test_build_system_always_has_omit_guidance_even_without_list():
    s = agent.build_system(_now(), [])
    assert "省略 calendar" in s
    assert "不要自己編" in s


def test_build_system_lists_calendars_when_available():
    s = agent.build_system(_now(), ["工作"])
    assert "可用日曆" in s and "工作" in s
    assert "省略 calendar" in s          # 指引仍在


@pytest.fixture(autouse=True)
def _reset():
    agent.reset()
    yield
    agent.reset()


def test_begin_create_rejects_unknown_calendar_shows_picker(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "")
    monkeypatch.setattr(agent, "_writable_calendars", lambda: ["居家", "工作"])
    out = agent._begin_create({"title": "X", "start": "2026-07-15", "end": "2026-07-15",
                               "all_day": True, "calendar": "default"})
    assert "哪一本" in out and "1. 居家" in out       # 不採信 default → 出選單


def test_begin_create_honors_known_calendar(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "")
    monkeypatch.setattr(agent, "_writable_calendars", lambda: ["居家", "工作"])
    out = agent._begin_create({"title": "X", "start": "2026-07-15T10:00",
                               "end": "2026-07-15T11:00", "calendar": "工作"})
    assert "【工作】" in out and "哪一本" not in out


def test_begin_create_empty_list_no_calendar_degrades(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "")
    monkeypatch.setattr(agent, "_writable_calendars", lambda: [])
    out = agent._begin_create({"title": "出差", "start": "2026-07-15",
                               "end": "2026-07-16", "all_day": True})
    assert "預設" in out and "yes" in out.lower()
    assert agent._pending["p"]["calendar"] == ""      # pending 用空字串 → 系統第一本


def test_begin_create_empty_list_trusts_explicit_calendar(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "")
    monkeypatch.setattr(agent, "_writable_calendars", lambda: [])
    out = agent._begin_create({"title": "X", "start": "2026-07-15", "end": "2026-07-15",
                               "all_day": True, "calendar": "工作"})
    assert "【工作】" in out                            # 清單拿不到也不抹掉使用者明講的日曆


def test_begin_create_empty_list_uses_config_default(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "工作")
    monkeypatch.setattr(agent, "_writable_calendars", lambda: [])
    out = agent._begin_create({"title": "X", "start": "2026-07-15", "end": "2026-07-15", "all_day": True})
    assert "【工作】" in out


def test_warm_calendars_populates_cache(monkeypatch):
    monkeypatch.setattr(cal, "list_calendars", lambda: ["A"])
    agent.reset()
    agent.warm_calendars()
    assert agent._writable_calendars() == ["A"]        # 快取已填、無需再打 osascript
