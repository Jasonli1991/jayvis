from panel import env_io
from panel.app import app


def _client(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    return app.test_client()


def test_actions_get_includes_search_enabled(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert "search_enabled" in c.get("/api/actions").get_json()


def test_actions_post_persists_search_enabled(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/actions", json={"search_enabled": True},
               headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code != 403
    assert c.get("/api/actions").get_json()["search_enabled"] is True


def test_tavily_key_boolean_only(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/api/llm-keys").get_json()["tavily"] is False
    c.post("/api/llm-keys", json={"tavily": "tvly-secret"},
           headers={"Origin": "http://127.0.0.1:8765"})
    j = c.get("/api/llm-keys").get_json()
    assert j["tavily"] is True                       # 只回布林
    assert "tvly-secret" not in c.get("/api/llm-keys").get_data(as_text=True)  # 不外洩明文


import panel.app as _appmod
from panel import env_io as _eio2


def test_sources_api_includes_code_root(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("", encoding="utf-8")
    monkeypatch.setattr(_eio2, "ENV_PATH", envf)
    c = _appmod.app.test_client()
    c.post("/api/sources",
           json={"obsidian_path": "/v", "github_repos": ["o/r"], "code_root": "/Users/x/MyProjects"},
           headers={"Origin": "http://127.0.0.1:8765"})
    assert c.get("/api/sources").get_json()["code_root"] == "/Users/x/MyProjects"
