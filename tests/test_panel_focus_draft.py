import focus_draft
from panel import env_io
from panel.app import app


def test_focus_draft_ok(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    monkeypatch.setattr(focus_draft, "draft", lambda brief, model=None: {"ok": True, "draft": "草稿X"})
    r = app.test_client().post("/api/leave/focus-draft", json={"brief": "X"})
    assert r.status_code == 200 and r.get_json()["draft"] == "草稿X"


def test_focus_draft_error_not_500(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    monkeypatch.setattr(focus_draft, "draft", lambda brief, model=None: {"ok": False, "error": "沒有素材"})
    r = app.test_client().post("/api/leave/focus-draft", json={"brief": ""})
    assert r.status_code == 200 and r.get_json()["ok"] is False


def test_focus_draft_exception_not_500(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    def boom(brief, model=None):
        raise RuntimeError("x")
    monkeypatch.setattr(focus_draft, "draft", boom)
    r = app.test_client().post("/api/leave/focus-draft", json={"brief": "x"})
    assert r.status_code == 200 and r.get_json()["ok"] is False
