from panel import env_io
from panel.app import app


def test_llm_keys_get_returns_bools_only(tmp_path, monkeypatch):
    """安全關鍵：讀取端永不回傳金鑰本體，只回設定狀態布林。"""
    envf = tmp_path / ".env"
    envf.write_text("GEMINI_API_KEY=super-secret-g\nANTHROPIC_API_KEY=super-secret-a\n",
                    encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    r = app.test_client().get("/api/llm-keys")
    assert r.status_code == 200
    assert "super-secret" not in r.get_data(as_text=True)
    assert r.get_json() == {"gemini": True, "anthropic": True, "openai": False, "tavily": False}


def test_llm_keys_post_writes_nonempty_only(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    r = app.test_client().post("/api/llm-keys", json={"openai": "o-9", "gemini": ""})
    assert r.status_code == 200
    text = envf.read_text()
    assert "o-9" in text and "GEMINI" not in text
