import analysis
import panel.app as app_mod
from panel import env_io


def test_analyze_uses_passed_model(monkeypatch):
    """analyze 可指定模型；給定就用給定的，不回退 config。"""
    seen = {}
    monkeypatch.setattr(analysis, "_open_conn", lambda: _FakeConn())
    monkeypatch.setattr(analysis, "hybrid_search", lambda conn, q, owner, out_k: [_Cand()])
    monkeypatch.setattr(analysis, "generate",
                        lambda model, system, messages, max_output_tokens: seen.setdefault("model", model) or "ans")
    analysis.analyze("q", model="gemini-2.5-flash")
    assert seen["model"] == "gemini-2.5-flash"


def test_api_analyze_passes_live_env_model(tmp_path, monkeypatch):
    """面板分析即時讀 .env 的 MODEL_CODE（改了不必重啟面板）。"""
    envf = tmp_path / ".env"
    envf.write_text("MODEL_CODE=gemini-2.5-flash\n", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    seen = {}
    monkeypatch.setattr(app_mod.analysis, "analyze",
                        lambda q, model=None: seen.update(q=q, model=model) or {"answer": "a", "sources": []})
    r = app_mod.app.test_client().post("/api/analyze", json={"query": "測試"})
    assert r.status_code == 200
    assert seen["model"] == "gemini-2.5-flash"


def test_analyze_default_owner_matches_ingest(monkeypatch):
    """分析預設 owner 必須與 ingest/schema 寫入的 'owner' 一致（否則撈 0 筆 → 永遠資料不足）。"""
    seen = {}
    monkeypatch.setattr(analysis, "_open_conn", lambda: _FakeConn())
    monkeypatch.setattr(analysis, "hybrid_search",
                        lambda conn, q, owner, out_k: seen.update(owner=owner) or [])
    analysis.analyze("q")
    assert seen["owner"] == "owner"


def test_owner_profile_has_no_partition_key():
    """單庫單人不需要分區鍵：owner_key 應已從身份檔移除。"""
    import persona
    p = persona.load_profile()       # owner_profile.json，未設定時退回 .example
    assert "owner_key" not in p


class _FakeConn:
    def close(self):
        pass


class _Cand:
    source_type = "obsidian"
    raw_text = "x"
    meta = {"doc_path": "a.md"}
