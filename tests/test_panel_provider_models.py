import llm
from panel.app import app


def test_provider_models_ok(monkeypatch):
    monkeypatch.setattr(llm, "list_available_models",
                        lambda: {"models": ["claude-opus-4-8", "gpt-4.1"], "providers": {"anthropic": 1, "openai": 1}})
    c = app.test_client()
    r = c.get("/api/provider-models")
    assert r.status_code == 200
    body = r.get_json()
    assert body["models"] == ["claude-opus-4-8", "gpt-4.1"]
    assert body["providers"] == {"anthropic": 1, "openai": 1}


def test_provider_models_never_500(monkeypatch):
    def boom():
        raise RuntimeError("list failed")
    monkeypatch.setattr(llm, "list_available_models", boom)
    c = app.test_client()
    r = c.get("/api/provider-models")
    assert r.status_code == 200                       # 容錯，不 500
    assert r.get_json() == {"models": [], "providers": {}}
