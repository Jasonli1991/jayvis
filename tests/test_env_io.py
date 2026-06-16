from pathlib import Path
import panel.env_io as env_io


def _setup(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=secret-keep\n", encoding="utf-8")
    wf = tmp_path / "WeeklyFocus.md"
    monkeypatch.setattr(env_io, "ENV_PATH", str(env))
    monkeypatch.setattr(env_io, "WEEKLYFOCUS_PATH", wf)
    return env, wf


def test_allowlist_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(env_io, "ALLOWLIST_PATH", tmp_path / "allowlist.json")
    env_io.write_allowlist([{"id": 111, "alias": "Morgan"}, {"id": 222, "alias": ""}])
    assert env_io.read_allowlist() == [{"id": 111, "alias": "Morgan"}, {"id": 222, "alias": ""}]


def test_sources_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    env_io.write_sources("/x/My Vault", ["a/b", "c/d"])
    s = env_io.read_sources()
    assert s["obsidian_path"] == "/x/My Vault"
    assert s["github_repos"] == ["a/b", "c/d"]
    env_io.write_sources("/y", [])           # 空 repos
    assert env_io.read_sources()["github_repos"] == []


def test_models_openai_base_url_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    env_io.write_models("g", "c", "0.3", openai_base_url="https://llm.siraya.ai/v1")
    assert env_io.read_models()["openai_base_url"] == "https://llm.siraya.ai/v1"
    env_io.write_models("g", "c", "0.3", openai_base_url="")   # 清空＝回官方端點
    assert env_io.read_models()["openai_base_url"] == ""


def test_llm_keys_roundtrip_and_blank_keep(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    env_io.write_llm_keys({"gemini": "g-1", "anthropic": "a-1", "openai": ""})
    assert env_io.read_llm_keys() == {"gemini": True, "anthropic": True, "openai": False, "tavily": False}
    env_io.write_llm_keys({"gemini": "", "anthropic": "a-2", "openai": "o-1"})  # 留空＝不變更
    assert env_io.read_llm_keys() == {"gemini": True, "anthropic": True, "openai": True, "tavily": False}


def test_models_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    env_io.write_models("gen-x", "code-y", "0.4")
    m = env_io.read_models()
    assert m == {"general": "gen-x", "code": "code-y", "threshold": "0.4",
                 "openai_base_url": ""}


def test_leave_roundtrip(tmp_path, monkeypatch):
    _, wf = _setup(tmp_path, monkeypatch)
    env_io.write_leave("2026-07-01", "2026-07-05", "# 本週重點\n\n- 做 X")
    got = env_io.read_leave()
    assert got["leave_start"] == "2026-07-01"
    assert got["leave_end"] == "2026-07-05"
    assert "做 X" in got["focus"]
    assert "leave_start: 2026-07-01" in wf.read_text()
