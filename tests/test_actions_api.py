from panel import env_io
import panel.app as app_mod


def _env(tmp_path, monkeypatch, content=""):
    envf = tmp_path / ".env"
    envf.write_text(content, encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    return envf


def test_get_actions_defaults(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "")
    j = app_mod.app.test_client().get("/api/actions").get_json()
    assert j == {"enabled": False, "calendar_name": "", "email_enabled": False,
                 "mail_account": "", "media_enabled": False, "search_enabled": False}


def test_post_actions_writes(tmp_path, monkeypatch):
    envf = _env(tmp_path, monkeypatch, "")
    app_mod.app.test_client().post("/api/actions", json={
        "enabled": True, "calendar_name": "工作", "email_enabled": True, "mail_account": "me@x.com",
        "media_enabled": True})
    txt = envf.read_text()
    assert "ACTIONS_ENABLED=true" in txt and "CALENDAR_NAME=工作" in txt
    assert "EMAIL_ENABLED=true" in txt and "MAIL_ACCOUNT=me@x.com" in txt
    assert "MEDIA_ENABLED=true" in txt
    assert app_mod.app.test_client().get("/api/actions").get_json() == {
        "enabled": True, "calendar_name": "工作", "email_enabled": True, "mail_account": "me@x.com",
        "media_enabled": True, "search_enabled": False}


def test_owner_api(tmp_path, monkeypatch):
    envf = _env(tmp_path, monkeypatch, "")
    assert app_mod.app.test_client().get("/api/owner").get_json() == {"owner_chat_id": ""}
    app_mod.app.test_client().post("/api/owner", json={"owner_chat_id": "6803"})
    assert "OWNER_CHAT_ID=6803" in envf.read_text()
    assert app_mod.app.test_client().get("/api/owner").get_json() == {"owner_chat_id": "6803"}
