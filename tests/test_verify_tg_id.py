import panel.app as app_mod
from panel import env_io


def _env(tmp_path, monkeypatch, content=""):
    envf = tmp_path / ".env"
    envf.write_text(content, encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))


def _get(tg_id):
    return app_mod.app.test_client().get("/api/verify-tg-id?id=" + tg_id).get_json()


def test_verify_bad_format(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "TG_BOT_TOKEN=x\n")
    assert _get("abc")["reason"] == "bad_format"
    assert _get("")["reason"] == "bad_format"


def test_verify_no_token(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "")              # 沒設 token
    j = _get("123456789")
    assert j["ok"] is False and j["reason"] == "no_token"


def test_verify_found(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "TG_BOT_TOKEN=x\n")
    monkeypatch.setattr(app_mod, "_tg_get_chat",
                        lambda token, tg_id: {"ok": True, "result": {"first_name": "Eric", "username": "eric"}})
    j = _get("123456789")
    assert j["ok"] is True and j["name"] == "Eric" and j["username"] == "@eric"


def test_verify_not_found(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "TG_BOT_TOKEN=x\n")
    monkeypatch.setattr(app_mod, "_tg_get_chat", lambda token, tg_id: {"ok": False, "error_code": 400})
    assert _get("123456789")["reason"] == "not_found"


def test_verify_bad_token(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "TG_BOT_TOKEN=x\n")
    monkeypatch.setattr(app_mod, "_tg_get_chat", lambda token, tg_id: {"ok": False, "error_code": 401})
    assert _get("123456789")["reason"] == "bad_token"


def test_verify_does_not_leak_token(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "TG_BOT_TOKEN=SECRET123\n")
    monkeypatch.setattr(app_mod, "_tg_get_chat", lambda token, tg_id: {"ok": False, "error_code": 400})
    body = app_mod.app.test_client().get("/api/verify-tg-id?id=123456789").get_data(as_text=True)
    assert "SECRET123" not in body
