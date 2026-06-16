from datetime import date

from panel import env_io


def test_status_on_duty_when_no_range(tmp_path, monkeypatch):
    f = tmp_path / "WeeklyFocus.md"
    f.write_text("---\nleave_start: \nleave_end: \n---\n本週重點", encoding="utf-8")
    monkeypatch.setattr(env_io, "WEEKLYFOCUS_PATH", f)
    monkeypatch.setattr(env_io, "_today", lambda: date(2026, 6, 9))
    d = env_io.read_leave()
    assert d["status"].startswith("在職")
    assert d["focus"] == "本週重點"


def test_status_on_leave_within_range(tmp_path, monkeypatch):
    f = tmp_path / "WeeklyFocus.md"
    f.write_text("---\nleave_start: 2026-06-20\nleave_end: 2026-06-25\n---\nx", encoding="utf-8")
    monkeypatch.setattr(env_io, "WEEKLYFOCUS_PATH", f)
    monkeypatch.setattr(env_io, "_today", lambda: date(2026, 6, 22))
    d = env_io.read_leave()
    assert "請假中" in d["status"]
    assert d["leave_start"] == "2026-06-20" and d["leave_end"] == "2026-06-25"


def test_status_on_duty_before_range(tmp_path, monkeypatch):
    f = tmp_path / "WeeklyFocus.md"
    f.write_text("---\nleave_start: 2026-06-20\nleave_end: 2026-06-25\n---\nx", encoding="utf-8")
    monkeypatch.setattr(env_io, "WEEKLYFOCUS_PATH", f)
    monkeypatch.setattr(env_io, "_today", lambda: date(2026, 6, 10))
    assert env_io.read_leave()["status"].startswith("在職")


def test_write_round_trip(tmp_path, monkeypatch):
    f = tmp_path / "WeeklyFocus.md"
    monkeypatch.setattr(env_io, "WEEKLYFOCUS_PATH", f)
    env_io.write_leave("2026-07-01", "2026-07-05", "重點A")
    d = env_io.read_leave()
    assert d["leave_start"] == "2026-07-01" and d["leave_end"] == "2026-07-05" and d["focus"] == "重點A"


def test_migrate_old_return_date(tmp_path, monkeypatch):
    f = tmp_path / "WeeklyFocus.md"
    f.write_text("---\nstatus: x\nreturn_date: 2026-08-01\n---\nbody", encoding="utf-8")
    monkeypatch.setattr(env_io, "WEEKLYFOCUS_PATH", f)
    monkeypatch.setattr(env_io, "_today", lambda: date(2026, 6, 9))
    assert env_io.read_leave()["leave_end"] == "2026-08-01"   # 舊欄位遷移成 end
