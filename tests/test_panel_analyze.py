import webbrowser

import analysis
from panel import env_io
from panel.app import app


def test_analyze_generates_and_opens(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    monkeypatch.setattr(analysis, "generate_report",
                        lambda q, model=None: {"ok": True, "path": "/x/r.html", "filename": "r.html"})
    opened = {}
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.update(u=u))
    r = app.test_client().post("/api/analyze", json={"query": "分析我的專案"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert opened["u"] == "file:///x/r.html"


def test_analyze_error_not_500(monkeypatch):
    monkeypatch.setattr(env_io, "read_models", lambda: {"code": "m", "general": "g", "threshold": 0.3})
    monkeypatch.setattr(analysis, "generate_report",
                        lambda q, model=None: {"ok": False, "error": "Obsidian 路徑沒設好"})
    r = app.test_client().post("/api/analyze", json={"query": "分析"})
    assert r.status_code == 200 and r.get_json()["ok"] is False


def test_analyze_empty_query():
    r = app.test_client().post("/api/analyze", json={"query": ""})
    assert r.status_code == 400
