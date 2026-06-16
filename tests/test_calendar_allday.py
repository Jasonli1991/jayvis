import calendar_tool as ct


def test_script_create_all_day_sets_allday_property():
    s = ct._script_create("Home", "台北出差", "2026-07-15", "2026-07-16", "", all_day=True)
    assert "allday event:true" in s
    assert "set day of d1 to 15" in s
    assert "set day of d2 to 16" in s


def test_script_create_timed_has_no_allday():
    s = ct._script_create("Home", "開會", "2026-07-15T10:00", "2026-07-15T11:00", "")
    assert "allday event" not in s
    assert "set hours of d1 to 10" in s


def test_create_event_threads_all_day(monkeypatch):
    seen = {}
    monkeypatch.setattr(ct, "_run", lambda script: seen.update(script=script) or "UID1")
    ct.create_event("出差", "2026-07-15", "2026-07-16", all_day=True)
    assert "allday event:true" in seen["script"]
