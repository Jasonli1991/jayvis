import assistant


def test_leave_status_line(monkeypatch):
    monkeypatch.setattr(assistant._leave_io, "read_leave", lambda: {"status": "請假中（2026-06-20 ~ 2026-06-25）"})
    assert "請假中" in assistant._leave_status_line()


def test_leave_status_line_swallows_errors(monkeypatch):
    def boom():
        raise RuntimeError("x")
    monkeypatch.setattr(assistant._leave_io, "read_leave", boom)
    assert assistant._leave_status_line() == ""
