import config
import focus_draft


def test_draft_failfast_all_empty(monkeypatch):
    monkeypatch.setattr(focus_draft, "_recent_conversations", lambda *a, **k: "")
    monkeypatch.setattr(focus_draft.github_sync, "get_project_status", lambda: "")
    monkeypatch.setattr(focus_draft, "_recent_obsidian", lambda *a, **k: "")
    monkeypatch.setattr(focus_draft, "_profile_context", lambda: "")
    gen = {"n": 0}
    monkeypatch.setattr(focus_draft, "generate", lambda **k: gen.__setitem__("n", 1) or "x")
    r = focus_draft.draft("")
    assert r["ok"] is False and "方向" in r["error"] and gen["n"] == 0   # 不碰 LLM


def test_draft_from_notes_only_no_commits(monkeypatch):
    # 行政用戶：無 commit、無對話，但有近期筆記 → 仍擬得出
    monkeypatch.setattr(focus_draft, "_recent_conversations", lambda *a, **k: "")
    monkeypatch.setattr(focus_draft.github_sync, "get_project_status", lambda: "")
    monkeypatch.setattr(focus_draft, "_recent_obsidian", lambda *a, **k: "近期筆記內容")
    monkeypatch.setattr(focus_draft, "_profile_context", lambda: "")
    seen = {}
    monkeypatch.setattr(focus_draft, "generate",
                        lambda **k: seen.update(user=k["messages"][0]["content"]) or "草稿OK")
    r = focus_draft.draft("")
    assert r["ok"] is True and r["draft"] == "草稿OK" and "近期筆記內容" in seen["user"]


def test_draft_includes_conversations_commits_brief(monkeypatch):
    monkeypatch.setattr(focus_draft, "_recent_conversations", lambda *a, **k: "對話片段")
    monkeypatch.setattr(focus_draft.github_sync, "get_project_status", lambda: "commit清單")
    monkeypatch.setattr(focus_draft, "_recent_obsidian", lambda *a, **k: "")
    monkeypatch.setattr(focus_draft, "_profile_context", lambda: "")
    seen = {}
    monkeypatch.setattr(focus_draft, "generate",
                        lambda **k: seen.update(user=k["messages"][0]["content"]) or "d")
    focus_draft.draft("這週主推X")
    assert "對話片段" in seen["user"] and "commit清單" in seen["user"] and "這週主推X" in seen["user"]


def test_recent_obsidian_queries_by_event_time(monkeypatch):
    class _Conn:
        def execute(self, sql, params):
            assert "source_type='obsidian'" in sql and "event_time DESC" in sql
            return type("C", (), {"fetchall": lambda s: [{"raw_text": "筆記A"}, {"raw_text": "筆記B"}]})()
        def close(self): pass
    monkeypatch.setattr(focus_draft, "get_conn", lambda: _Conn())
    out = focus_draft._recent_obsidian()
    assert "筆記A" in out and "筆記B" in out
