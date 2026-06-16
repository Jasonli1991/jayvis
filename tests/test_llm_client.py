import config
import llm


def test_google_client_uses_api_key_when_set(monkeypatch):
    calls = {}
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k-123")
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(llm.genai, "Client", lambda **kw: calls.update(kw) or object())
    llm._get_client("google")
    assert calls.get("api_key") == "k-123" and "vertexai" not in calls


def test_google_client_uses_vertex_when_no_key(monkeypatch):
    calls = {}
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(llm.genai, "Client", lambda **kw: calls.update(kw) or object())
    llm._get_client("google")
    assert calls.get("vertexai") is True and "api_key" not in calls
