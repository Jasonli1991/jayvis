from panel import env_io
from panel.app import app


def test_bot_token_get_returns_bool_only(tmp_path, monkeypatch):
    """安全：讀取端永不回 token 本體，只回是否已設定。"""
    envf = tmp_path / ".env"
    envf.write_text("TG_BOT_TOKEN=8486403833:SUPER_SECRET_TOKEN\n", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    r = app.test_client().get("/api/bot-token")
    assert r.status_code == 200
    assert "SUPER_SECRET_TOKEN" not in r.get_data(as_text=True)
    assert r.get_json() == {"set": True}


def test_bot_token_get_unset(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    assert app.test_client().get("/api/bot-token").get_json() == {"set": False}


def test_bot_token_post_writes_nonempty_only(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("TG_BOT_TOKEN=old-token\n", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    # 留空＝不變更
    app.test_client().post("/api/bot-token", json={"token": ""})
    assert "old-token" in envf.read_text()
    # 有值＝覆寫
    app.test_client().post("/api/bot-token", json={"token": "new-token-123"})
    assert "new-token-123" in envf.read_text() and "old-token" not in envf.read_text()
