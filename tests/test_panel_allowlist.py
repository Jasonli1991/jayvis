import browse_allowlist as ba
from panel import env_io
from panel.app import app


def test_browse_allowlist_get_post_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ba, "_PATH", tmp_path / "browse_allowlist.json")
    c = app.test_client()

    r = c.get("/api/browse/allowlist")
    assert r.status_code == 200
    assert r.get_json() == {"domains": []}

    r = c.post("/api/browse/allowlist", json={"domains": ["example.com", "example.com"]})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    r = c.get("/api/browse/allowlist")
    assert r.get_json() == {"domains": ["example.com"]}     # 去重後


def test_browse_allowlist_post_rejects_non_list(tmp_path, monkeypatch):
    monkeypatch.setattr(ba, "_PATH", tmp_path / "browse_allowlist.json")
    c = app.test_client()
    r = c.post("/api/browse/allowlist", json={"domains": "oops"})
    assert r.status_code == 400
    assert "domains must be a list" in r.get_json()["error"]


def test_browse_enabled_get_post_roundtrip(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    c = app.test_client()

    assert c.get("/api/browse/enabled").get_json() == {"enabled": False}   # 預設關

    r = c.post("/api/browse/enabled", json={"enabled": True})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert c.get("/api/browse/enabled").get_json() == {"enabled": True}
    assert "BROWSE_ENABLED=true" in envf.read_text()                       # 真的寫進 .env

    c.post("/api/browse/enabled", json={"enabled": False})
    assert c.get("/api/browse/enabled").get_json() == {"enabled": False}
