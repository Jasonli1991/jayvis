import leave_digest
from panel import env_io
from panel.app import app


def test_leave_digest_ok_sends(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    monkeypatch.setattr(leave_digest, "compile_digest", lambda model=None: {"ok": True, "summary": "彙整X"})
    sent = {"n": 0}
    monkeypatch.setattr(leave_digest, "send_to_owner", lambda t: sent.__setitem__("n", 1) or True)
    r = app.test_client().post("/api/leave/digest")
    b = r.get_json()
    assert r.status_code == 200 and b["ok"] is True and b["summary"] == "彙整X" and b["tg_sent"] is True
    assert sent["n"] == 1


def test_leave_digest_error_not_500(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    monkeypatch.setattr(leave_digest, "compile_digest", lambda model=None: {"ok": False, "error": "尚未設定請假期間"})
    r = app.test_client().post("/api/leave/digest")
    assert r.status_code == 200 and r.get_json()["ok"] is False


def test_leave_digest_exception_not_500(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    def boom(model=None):
        raise RuntimeError("x")
    monkeypatch.setattr(leave_digest, "compile_digest", boom)
    r = app.test_client().post("/api/leave/digest")
    assert r.status_code == 200 and r.get_json()["ok"] is False
