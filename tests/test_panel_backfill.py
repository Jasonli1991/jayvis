import panel.app as app_mod
from panel import env_io


class _FakeConn:
    def close(self):
        pass


def _setup(tmp_path, monkeypatch, env_content):
    envf = tmp_path / ".env"
    envf.write_text(env_content, encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))
    monkeypatch.setattr(app_mod, "get_conn", lambda: _FakeConn())
    monkeypatch.setattr(app_mod, "apply_schema", lambda c: None)


def test_backfill_obsidian_uses_live_env_path(tmp_path, monkeypatch):
    """面板剛存的路徑要立即生效（不重啟 panel）→ 重灌須即時讀 .env"""
    _setup(tmp_path, monkeypatch, "OBSIDIAN_PATH=/fresh/vault\n")
    seen = {}
    monkeypatch.setattr(app_mod, "ingest_dir", lambda conn, path: seen.update(path=path) or 7)
    app_mod._run_backfill("obsidian")
    assert seen["path"] == "/fresh/vault"
    assert "7" in app_mod._backfill["last"]


def test_backfill_obsidian_warns_when_path_has_no_notes(tmp_path, monkeypatch):
    """掃到 0 檔 → 應警告路徑問題，而不是含糊的「寫入 0」"""
    _setup(tmp_path, monkeypatch, "OBSIDIAN_PATH=/empty/place\n")
    monkeypatch.setattr(app_mod, "ingest_dir", lambda conn, path: 0)
    monkeypatch.setattr(app_mod, "count_md_files", lambda path: 0)
    app_mod._run_backfill("obsidian")
    assert "找不到" in app_mod._backfill["last"]


def test_backfill_obsidian_uptodate_when_no_changes(tmp_path, monkeypatch):
    """掃到 N 檔但寫入 0 → 應顯示「已是最新」"""
    _setup(tmp_path, monkeypatch, "OBSIDIAN_PATH=/real/vault\n")
    monkeypatch.setattr(app_mod, "ingest_dir", lambda conn, path: 0)
    monkeypatch.setattr(app_mod, "count_md_files", lambda path: 116)
    app_mod._run_backfill("obsidian")
    assert "已是最新" in app_mod._backfill["last"]
    assert "116" in app_mod._backfill["last"]


def test_pick_folder_returns_501_without_native_window():
    """測試環境沒有 pywebview 視窗 → 應回 501（前端據此提示手動貼路徑）"""
    r = app_mod.app.test_client().post("/api/pick-folder")
    assert r.status_code == 501
    assert "error" in r.get_json()


def test_pick_folder_returns_selected_path(monkeypatch):
    """有原生視窗時 → 回傳使用者選的資料夾"""
    class _FakeWin:
        def create_file_dialog(self, dialog_type, directory=""):
            return ("/Users/someone/MyVault",)
    monkeypatch.setattr(app_mod.webview, "windows", [_FakeWin()])
    r = app_mod.app.test_client().post("/api/pick-folder", json={})
    assert r.status_code == 200
    assert r.get_json()["path"] == "/Users/someone/MyVault"


def test_backfill_github_empty_env_disables(tmp_path, monkeypatch):
    """.env GITHUB_REPOS= 空字串 → 重灌 GitHub no-op，不該去 fetch"""
    _setup(tmp_path, monkeypatch, "GITHUB_REPOS=\n")
    monkeypatch.setattr(app_mod, "_fetch_commits",
                        lambda repo: (_ for _ in ()).throw(AssertionError("should not fetch")))
    app_mod._run_backfill("github")
    assert "0" in app_mod._backfill["last"]
