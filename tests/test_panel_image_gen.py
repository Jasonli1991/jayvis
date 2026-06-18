from panel import env_io
from panel.app import app


def test_image_gen_enabled_roundtrip(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    c = app.test_client()

    assert c.get("/api/image-gen/enabled").get_json() == {"enabled": False}   # 預設關
    r = c.post("/api/image-gen/enabled", json={"enabled": True})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert c.get("/api/image-gen/enabled").get_json() == {"enabled": True}
    assert "IMAGE_GEN_ENABLED=true" in envf.read_text()
    c.post("/api/image-gen/enabled", json={"enabled": False})
    assert c.get("/api/image-gen/enabled").get_json() == {"enabled": False}
