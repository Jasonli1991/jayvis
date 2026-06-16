from panel import env_io
from panel.app import app


def _client(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    return app.test_client()


def test_actions_get_includes_media_enabled(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    j = c.get("/api/actions").get_json()
    assert "media_enabled" in j


def test_actions_post_persists_media_enabled(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/actions", json={"media_enabled": True},
               headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code != 403
    assert c.get("/api/actions").get_json()["media_enabled"] is True
