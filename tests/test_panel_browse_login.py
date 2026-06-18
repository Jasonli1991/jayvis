import browse_launch
from panel.app import app


def test_login_begin(monkeypatch):
    monkeypatch.setattr(browse_launch, "begin_login", lambda: True)
    r = app.test_client().post("/api/browse/login/begin")
    assert r.status_code == 200 and r.get_json() == {"ok": True, "ready": True}


def test_login_end_calls_end_login(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(browse_launch, "end_login", lambda: calls.__setitem__("n", 1))
    r = app.test_client().post("/api/browse/login/end")
    assert r.status_code == 200 and r.get_json()["ok"] is True and calls["n"] == 1


def test_login_status(monkeypatch):
    monkeypatch.setattr(browse_launch, "is_login_mode", lambda: True)
    r = app.test_client().get("/api/browse/login/status")
    assert r.get_json() == {"login_mode": True}


def test_login_begin_never_500(monkeypatch):
    def boom():
        raise RuntimeError("launch failed")
    monkeypatch.setattr(browse_launch, "begin_login", boom)
    r = app.test_client().post("/api/browse/login/begin")
    assert r.status_code == 200 and r.get_json()["ok"] is False
