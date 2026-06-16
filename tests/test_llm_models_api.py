import panel.app as app_mod
from panel import env_io


def _env(tmp_path, monkeypatch, content):
    envf = tmp_path / ".env"
    envf.write_text(content, encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))


def test_models_listed_from_endpoint(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "OPENAI_BASE_URL=http://10.0.0.5:11435/v1\n")
    monkeypatch.setattr(app_mod, "_fetch_compat_models",
                        lambda base: ["gemma4:12b", "qwen3:8b"])
    r = app_mod.app.test_client().get("/api/llm-models")
    assert r.status_code == 200
    j = r.get_json()
    assert j["models"] == ["gemma4:12b", "qwen3:8b"]
    assert "11435" in j["endpoint"]


def test_models_base_query_param_overrides_env(tmp_path, monkeypatch):
    """?base=<url> 用當下欄位值（免先儲存就能預覽本地/區網模型）。"""
    _env(tmp_path, monkeypatch, "OPENAI_BASE_URL=http://192.168.0.1:11435/v1\n")
    monkeypatch.setattr(app_mod, "_fetch_compat_models",
                        lambda base: ["m1"] if "10.9.9.9" in base else ["saved-only"])
    j = app_mod.app.test_client().get("/api/llm-models?base=http://10.9.9.9:11435/v1").get_json()
    assert j["models"] == ["m1"]
    assert "10.9.9.9" in j["endpoint"]


def test_safe_base_allows_loopback_and_private():
    assert app_mod._safe_base("http://127.0.0.1:11435/v1")
    assert app_mod._safe_base("http://192.168.0.10:11435/v1")
    assert app_mod._safe_base("http://10.0.0.5:11435/v1")


def test_safe_base_blocks_metadata_external_and_bad_scheme():
    assert not app_mod._safe_base("http://169.254.169.254/latest/meta-data")   # 雲端 metadata
    assert not app_mod._safe_base("http://1.2.3.4:11435/v1")                    # 外部位址
    assert not app_mod._safe_base("http://8.8.8.8/")
    assert not app_mod._safe_base("ftp://127.0.0.1/x")                          # 非 http
    assert not app_mod._safe_base("file:///etc/passwd")


def test_models_blocks_unsafe_base_param(tmp_path, monkeypatch):
    """?base=<外部/metadata> → 擋掉（SSRF 防護），不去 fetch。"""
    _env(tmp_path, monkeypatch, "")
    called = {"n": 0}
    monkeypatch.setattr(app_mod, "_fetch_compat_models", lambda base: called.update(n=1) or ["x"])
    j = app_mod.app.test_client().get("/api/llm-models?base=http://169.254.169.254/v1").get_json()
    assert j["models"] == [] and j.get("error") == "blocked"
    assert called["n"] == 0                       # 根本沒去 fetch


def test_status_includes_version():
    s = app_mod.app.test_client().get("/api/status").get_json()
    assert s.get("version") and isinstance(s["version"], str)


def test_status_models_reflect_live_env(tmp_path, monkeypatch):
    """狀態徽章要即時反映 .env 的模型，而非面板啟動時凍結的 config。"""
    _env(tmp_path, monkeypatch, "MODEL_GENERAL=qwen3:8b\nMODEL_CODE=qwen3:8b\n")
    s = app_mod.app.test_client().get("/api/status").get_json()
    assert s["models"]["general"] == "qwen3:8b"
    assert s["models"]["code"] == "qwen3:8b"


def test_models_empty_when_no_endpoint(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, "")
    r = app_mod.app.test_client().get("/api/llm-models")
    assert r.get_json() == {"models": [], "endpoint": ""}


def test_models_empty_when_unreachable(tmp_path, monkeypatch):
    """離公司網路：端點打不到 → 回空清單，不可 500、不可卡住。"""
    _env(tmp_path, monkeypatch, "OPENAI_BASE_URL=http://10.0.0.1:11435/v1\n")

    def _boom(base):
        raise OSError("unreachable")

    monkeypatch.setattr(app_mod, "_fetch_compat_models", _boom)
    r = app_mod.app.test_client().get("/api/llm-models")
    assert r.status_code == 200
    assert r.get_json()["models"] == []


def test_fetch_compat_models_parses_openai_shape(monkeypatch):
    """_fetch_compat_models 解析 OpenAI /models 格式並排序 id。"""
    import io
    import json as _json

    payload = _json.dumps({"data": [{"id": "qwen3:8b"}, {"id": "gemma4:12b"}, {"id": ""}]})

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *a):
            self.close()

    monkeypatch.setattr(app_mod.urllib.request, "urlopen",
                        lambda url, timeout=3: _Resp(payload.encode()))
    out = app_mod._fetch_compat_models("http://x:11435/v1")
    assert out == ["gemma4:12b", "qwen3:8b"]    # 排序、空 id 濾掉
