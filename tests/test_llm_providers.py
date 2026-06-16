import base64

import pytest

import config
import llm


# ── provider 判定 ─────────────────────────────────────────────
@pytest.mark.parametrize("model,provider", [
    ("gemini-2.5-flash", "google"),
    ("gemini-2.5-pro", "google"),
    ("claude-opus-4-8", "anthropic"),
    ("claude-haiku-4-5", "anthropic"),
    ("gpt-5", "openai"),
    ("o3-mini", "openai"),
    ("my-custom-model", "google"),     # 未知 → google fallback（無自訂端點時）
])
def test_provider_of(model, provider, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "")
    assert llm._provider_of(model) == provider


def test_unknown_model_routes_to_custom_endpoint(monkeypatch):
    """設了 OPENAI_BASE_URL（如 siraya）→ 非 gemini/claude 模型一律走相容端點。"""
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "https://llm.siraya.ai/v1")
    assert llm._provider_of("deepseek-r1") == "openai"
    assert llm._provider_of("llama-3.3-70b") == "openai"
    assert llm._provider_of("gpt-4o") == "openai"
    assert llm._provider_of("gemini-2.5-flash") == "google"      # 不受影響
    assert llm._provider_of("claude-opus-4-8") == "anthropic"    # 不受影響


def test_openai_client_uses_custom_base_url(monkeypatch):
    import openai as openai_mod
    calls = {}
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "https://llm.siraya.ai/v1")
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(openai_mod, "OpenAI", lambda **kw: calls.update(kw) or object())
    llm._get_client("openai")
    assert calls["base_url"] == "https://llm.siraya.ai/v1"


def test_openai_client_default_base_url_when_unset(monkeypatch):
    import openai as openai_mod
    calls = {}
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "")
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(openai_mod, "OpenAI", lambda **kw: calls.update(kw) or object())
    llm._get_client("openai")
    assert calls.get("base_url") is None        # None＝官方預設端點


# ── 分派 ─────────────────────────────────────────────────────
def test_generate_dispatches_by_model(monkeypatch):
    calls = {}

    def _stub(name, ret):
        def f(**kw):
            calls[name] = kw
            return ret
        return f

    monkeypatch.setattr(llm, "_gen_anthropic", _stub("anthropic", "A"))
    monkeypatch.setattr(llm, "_gen_openai", _stub("openai", "O"))
    monkeypatch.setattr(llm, "_gen_google", _stub("google", "G"))
    assert llm.generate("claude-opus-4-8", "sys", [{"role": "user", "content": "hi"}]) == "A"
    assert llm.generate("gpt-5", "sys", [{"role": "user", "content": "hi"}]) == "O"
    assert llm.generate("gemini-2.5-flash", "sys", [{"role": "user", "content": "hi"}]) == "G"
    assert calls["anthropic"]["model"] == "claude-opus-4-8"
    assert calls["anthropic"]["system"] == "sys"


# ── 缺金鑰 ────────────────────────────────────────────────────
def test_missing_anthropic_key_raises(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm, "_clients", {})
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.generate("claude-opus-4-8", "sys", [{"role": "user", "content": "hi"}])


def test_missing_openai_key_raises(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "")
    monkeypatch.setattr(llm, "_clients", {})
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm.generate("gpt-5", "sys", [{"role": "user", "content": "hi"}])


def test_compat_endpoint_needs_no_key(monkeypatch):
    """本地 Ollama 等相容端點不需金鑰：沒填時用慣例假值 'ollama'，不報錯。"""
    import openai as openai_mod
    calls = {}
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "http://10.0.0.5:11435/v1")
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(openai_mod, "OpenAI", lambda **kw: calls.update(kw) or object())
    llm._get_client("openai")
    assert calls["api_key"] == "ollama"
    assert calls["base_url"] == "http://10.0.0.5:11435/v1"


# ── 訊息格式轉換（純函式） ────────────────────────────────────
def test_to_anthropic_messages_with_image():
    msgs = llm._to_anthropic_messages(
        [{"role": "user", "content": "看圖"}], image_bytes=b"\xff\xd8")
    assert msgs[-1]["role"] == "user"
    blocks = msgs[-1]["content"]
    types_ = [b["type"] for b in blocks]
    assert "image" in types_ and "text" in types_
    img = next(b for b in blocks if b["type"] == "image")
    assert img["source"]["type"] == "base64"
    assert img["source"]["media_type"] == "image/jpeg"
    assert img["source"]["data"] == base64.b64encode(b"\xff\xd8").decode()


def test_to_anthropic_messages_roles():
    msgs = llm._to_anthropic_messages(
        [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"},
         {"role": "user", "content": "q2"}], image_bytes=None)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == "a1"


def test_to_openai_messages_with_image():
    msgs = llm._to_openai_messages(
        "sys", [{"role": "user", "content": "看圖"}], image_bytes=b"\xff\xd8")
    assert msgs[0] == {"role": "system", "content": "sys"}
    parts = msgs[-1]["content"]
    url = next(p for p in parts if p["type"] == "image_url")["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
