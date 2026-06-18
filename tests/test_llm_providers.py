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
    # 明確帶官方端點（不傳 None）：避免空字串 OPENAI_BASE_URL 環境變數被 SDK 取走→空 URL
    assert calls.get("base_url") == "https://api.openai.com/v1"


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


# ── 額度耗盡偵測（429 / RESOURCE_EXHAUSTED / quota）──────────────
@pytest.mark.parametrize("msg,expected", [
    ("429 RESOURCE_EXHAUSTED", True),
    ("You exceeded your current quota", True),
    ("Error code: 429", True),
    ("resource_exhausted: quota", True),
    ("connection timeout", False),
    ("400 invalid argument", False),
])
def test_is_quota_error(msg, expected):
    assert llm.is_quota_error(RuntimeError(msg)) is expected


def test_quota_msg_points_to_routing():
    assert "模型路由" in llm.QUOTA_MSG and "429" in llm.QUOTA_MSG


# ── Gemma 思考型模型的輸出 token 下限 ──────────────────────────
def test_effective_max_tokens_floors_gemma():
    # Gemma 4 會先消耗思考 token；上限太小會被吃光→空輸出，故設下限
    assert llm._effective_max_tokens("gemma-4-31b-it", 60) == llm._GEMMA_MIN_OUTPUT_TOKENS
    assert llm._effective_max_tokens("gemma-4-26b-a4b-it", 8) == llm._GEMMA_MIN_OUTPUT_TOKENS


def test_effective_max_tokens_does_not_lower():
    # 已經夠大的請求不下調
    assert llm._effective_max_tokens("gemma-4-31b-it", 4096) == 4096


def test_effective_max_tokens_non_gemma_untouched():
    assert llm._effective_max_tokens("gemini-2.5-flash", 60) == 60
    assert llm._effective_max_tokens("claude-opus-4-8", 16) == 16


# ── OpenAI base_url：空值用官方端點（避免空字串環境變數毒化）──────
def test_openai_base_url_default_when_empty(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "")
    assert llm._openai_base_url() == "https://api.openai.com/v1"


def test_openai_base_url_respects_compat_endpoint(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "http://192.168.0.9:11435/v1")
    assert llm._openai_base_url() == "http://192.168.0.9:11435/v1"


# ── list_available_models：三家列對話模型、容錯、去重 ──────────
from types import SimpleNamespace as _NS


def _fake_google(items):
    # items: list of (name, supported_actions)
    objs = [_NS(name=n, supported_actions=a) for n, a in items]
    return _NS(models=_NS(list=lambda: iter(objs)))


def _fake_listdata(ids):
    return _NS(models=_NS(list=lambda: _NS(data=[_NS(id=i) for i in ids])))


def _patch_provider_clients(monkeypatch, google=None, anthropic=None, openai=None):
    mapping = {"google": google, "anthropic": anthropic, "openai": openai}

    def fake_get(provider):
        c = mapping[provider]
        if c is None:
            raise RuntimeError("client boom")
        return c

    monkeypatch.setattr(llm, "_get_client", fake_get)


def _keys(monkeypatch, g="", a="", o=""):
    monkeypatch.setattr(config, "GEMINI_API_KEY", g)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", a)
    monkeypatch.setattr(config, "OPENAI_API_KEY", o)


def test_list_google_filters_to_chat_generatecontent(monkeypatch):
    _keys(monkeypatch, g="k")
    g = _fake_google([
        ("models/gemini-2.5-flash", ["generateContent", "countTokens"]),
        ("models/gemma-4-31b-it", ["generateContent"]),
        ("models/gemini-2.5-flash-image", ["generateContent"]),         # image → 排除
        ("models/text-embedding-004", ["embedContent"]),                # 無 generateContent → 排除
        ("models/gemini-3.1-flash-tts-preview", ["generateContent"]),   # tts → 排除
    ])
    _patch_provider_clients(monkeypatch, google=g)
    out = llm.list_available_models()
    assert "gemini-2.5-flash" in out["models"] and "gemma-4-31b-it" in out["models"]
    assert "gemini-2.5-flash-image" not in out["models"]
    assert "text-embedding-004" not in out["models"]
    assert "gemini-3.1-flash-tts-preview" not in out["models"]
    assert out["providers"]["google"] == 2


def test_list_anthropic_takes_all(monkeypatch):
    _keys(monkeypatch, a="k")
    a = _fake_listdata(["claude-opus-4-8", "claude-fable-5"])
    _patch_provider_clients(monkeypatch, anthropic=a)
    out = llm.list_available_models()
    assert set(out["models"]) == {"claude-opus-4-8", "claude-fable-5"}
    assert out["providers"]["anthropic"] == 2


def test_list_openai_filters_to_chat(monkeypatch):
    _keys(monkeypatch, o="k")
    o = _fake_listdata(["gpt-4.1", "o3-mini", "text-embedding-3-small",
                        "gpt-4o-realtime-preview", "whisper-1", "gpt-3.5-turbo-instruct"])
    _patch_provider_clients(monkeypatch, openai=o)
    out = llm.list_available_models()
    assert "gpt-4.1" in out["models"] and "o3-mini" in out["models"]
    for bad in ("text-embedding-3-small", "gpt-4o-realtime-preview", "whisper-1", "gpt-3.5-turbo-instruct"):
        assert bad not in out["models"]


def test_list_skips_provider_without_key(monkeypatch):
    _keys(monkeypatch, a="k")              # 只有 anthropic 有金鑰
    a = _fake_listdata(["claude-opus-4-8"])
    _patch_provider_clients(monkeypatch, anthropic=a)   # google/openai 的 client 不會被取用
    out = llm.list_available_models()
    assert out["providers"] == {"anthropic": 1}


def test_list_tolerates_provider_failure(monkeypatch):
    _keys(monkeypatch, g="k", a="k")
    a = _fake_listdata(["claude-opus-4-8"])
    _patch_provider_clients(monkeypatch, google=None, anthropic=a)   # google 取 client 就爆
    out = llm.list_available_models()
    assert out["models"] == ["claude-opus-4-8"]        # google 失敗不影響 anthropic
    assert "google" not in out["providers"]


def test_list_dedups_and_sorts(monkeypatch):
    _keys(monkeypatch, a="k", o="k")
    a = _fake_listdata(["gpt-4.1", "claude-opus-4-8"])   # 故意與 openai 重疊一個
    o = _fake_listdata(["gpt-4.1", "o3-mini"])
    _patch_provider_clients(monkeypatch, anthropic=a, openai=o)
    out = llm.list_available_models()
    assert out["models"] == sorted(out["models"])       # 排序
    assert out["models"].count("gpt-4.1") == 1          # 去重
