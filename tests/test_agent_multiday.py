from datetime import datetime

import agent


def _wd(d):
    return agent._WD[datetime.fromisoformat(d).weekday()]


def test_fmt_when_allday_single():
    out = agent._fmt_when({"start": "2026-07-15", "end": "2026-07-15", "all_day": True})
    assert out == f"7/15（{_wd('2026-07-15')}）整天"


def test_fmt_when_allday_range_shows_both_dates():
    out = agent._fmt_when({"start": "2026-07-15", "end": "2026-07-16", "all_day": True})
    assert out == f"7/15（{_wd('2026-07-15')}）–7/16（{_wd('2026-07-16')}）整天"


def test_fmt_when_timed_same_day():
    out = agent._fmt_when({"start": "2026-07-15T15:00", "end": "2026-07-15T17:00"})
    assert out == "2026-07-15 15:00–17:00"


def test_fmt_when_timed_cross_day_shows_full_end():
    out = agent._fmt_when({"start": "2026-07-15T23:00", "end": "2026-07-16T01:00"})
    assert out == "2026-07-15 23:00 – 2026-07-16 01:00"


import pytest

import config
import calendar_tool as cal


def _now():
    return datetime(2026, 6, 11)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    agent.reset()
    monkeypatch.setattr(cal, "list_calendars", lambda: [])


def test_build_system_has_all_day_guidance():
    s = agent.build_system(_now(), ["工作"])
    assert "all_day" in s
    assert "整天" in s


def test_execute_create_threads_all_day_and_shows_range(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "家人共享")
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"create","title":"台北出差","start":"2026-07-15","end":"2026-07-16","all_day":true,"notes":""}')
    got = {}
    monkeypatch.setattr(cal, "create_event",
                        lambda title, start, end, notes="", calendar=None, all_day=False:
                        got.update(all_day=all_day, end=end) or {"uid": "X"})
    out1 = agent.handle("7/15-7/16 台北出差", _now())
    assert "整天" in out1 and "7/16" in out1          # 確認畫面顯示跨日整天
    out2 = agent.handle("yes", _now())
    assert got["all_day"] is True and got["end"] == "2026-07-16"
    assert "已新增" in out2
