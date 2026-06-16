import os
import sys

import pytest

import calendar_tool as ct


def test_create_event_returns_uid(monkeypatch):
    seen = {}

    def _fake_run(script):
        seen["script"] = script
        return "NEWUID"

    monkeypatch.setattr(ct, "_run", _fake_run)
    out = ct.create_event("與 Max 開會", "2026-06-15T15:00", "2026-06-15T16:00", calendar="Home")
    assert out["uid"] == "NEWUID"
    assert out["title"] == "與 Max 開會"
    assert 'summary:"與 Max 開會"' in seen["script"]


def test_list_events_parses(monkeypatch):
    raw = "U1" + ct.SEP + "午餐" + ct.SEP + "2026-06-15T12:00" + ct.SEP + "2026-06-15T13:00"
    monkeypatch.setattr(ct, "_run", lambda s: raw)
    evs = ct.list_events("2026-06-15T00:00", "2026-06-16T00:00", calendar="Home")
    assert evs == [{"uid": "U1", "title": "午餐", "start": "2026-06-15T12:00", "end": "2026-06-15T13:00"}]


def test_delete_event(monkeypatch):
    monkeypatch.setattr(ct, "_run", lambda s: "")
    assert ct.delete_event("U1", calendar="Home") == {"deleted": True}


def test_script_list_calendars_writable_only():
    s = ct._script_list_calendars()
    assert "whose writable is true" in s
    assert "name of c" in s


def test_list_calendars_parses(monkeypatch):
    monkeypatch.setattr(ct, "_run", lambda s, timeout=20: "居家\n工作\n行事曆\n")
    assert ct.list_calendars() == ["居家", "工作", "行事曆"]


def test_list_calendars_uses_longer_timeout(monkeypatch):
    # 列舉遠端日曆慢（實測 ~22s），需放寬逾時，否則 20s 上限會誤判「讀不到」
    seen = {}
    monkeypatch.setattr(ct, "_run", lambda s, timeout=20: seen.update(timeout=timeout) or "工作\n")
    ct.list_calendars()
    assert seen["timeout"] == 45


@pytest.mark.skipif(not os.getenv("RUN_CALENDAR") or sys.platform != "darwin",
                    reason="set RUN_CALENDAR=1 on macOS to hit real Calendar")
def test_real_create_list_delete_roundtrip():
    ev = ct.create_event("JAYVIS 測試", "2026-12-31T09:00", "2026-12-31T10:00", calendar="")
    found = [e for e in ct.list_events("2026-12-31T00:00", "2027-01-01T00:00", calendar="")
             if e["uid"] == ev["uid"]]
    assert found and found[0]["title"] == "JAYVIS 測試"
    assert ct.delete_event(ev["uid"], calendar="")["deleted"]
