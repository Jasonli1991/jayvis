"""解除安裝的安全測試。

重點：
- 只記「JAYVIS 真正裝的」（pre_existed=False 才記、去重）。
- remove 只刪「掃描提供的路徑」（manifest＋已知候選），任意路徑一律拒絕、不誤刪。
- 清資料保留 installed.json（卸載清單不被清資料砍掉）。
- 端點：bot 還在跑時擋下卸載。
"""
import config
import install_manifest
from panel import uninstall


def _tmp_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(install_manifest, "MANIFEST", tmp_path / "installed.json")


def test_record_if_new_only_records_new(monkeypatch, tmp_path):
    _tmp_manifest(monkeypatch, tmp_path)
    install_manifest.record_if_new("model", "/x/m", pre_existed=True, name="m")
    assert install_manifest.items() == []                 # 原本就有 → 不記（不會誤認成 JAYVIS 裝的）
    install_manifest.record_if_new("model", "/x/m", pre_existed=False, name="m")
    assert len(install_manifest.items()) == 1             # 新裝 → 記
    install_manifest.record_if_new("model", "/x/m", pre_existed=False, name="m")
    assert len(install_manifest.items()) == 1             # 同路徑去重


def test_remove_rejects_unlisted_path(monkeypatch, tmp_path):
    _tmp_manifest(monkeypatch, tmp_path)
    victim = tmp_path / "do-not-delete.txt"
    victim.write_text("important", encoding="utf-8")
    r = uninstall.remove([str(victim)], clear_data=False)
    assert r["results"][0]["ok"] is False                 # 不在允許清單 → 拒絕
    assert victim.exists()                                 # 絕不誤刪任意路徑


def test_remove_deletes_tracked_and_forgets(monkeypatch, tmp_path):
    _tmp_manifest(monkeypatch, tmp_path)
    target = tmp_path / "model-cache"
    target.mkdir()
    (target / "weights.bin").write_text("x", encoding="utf-8")
    install_manifest.record("model", str(target), name="m")     # 記成 JAYVIS 裝的
    r = uninstall.remove([str(target)], clear_data=False)
    assert r["results"][0]["ok"] is True
    assert not target.exists()                             # 已刪
    assert install_manifest.items() == []                  # manifest 也移除該筆


def test_clear_data_preserves_installed_manifest(monkeypatch, tmp_path):
    data = tmp_path / "ndir"
    data.mkdir()
    (data / "kb.sqlite").write_text("db", encoding="utf-8")
    (data / "allowlist.json").write_text("[]", encoding="utf-8")
    (data / "installed.json").write_text('{"items":[]}', encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr(install_manifest, "MANIFEST", data / "installed.json")
    uninstall.remove([], clear_data=True)
    assert not (data / "kb.sqlite").exists()               # 資料清掉
    assert not (data / "allowlist.json").exists()
    assert (data / "installed.json").exists()              # 卸載清單保留（之後仍能精準卸載）


def test_remove_endpoint_blocks_when_bot_running(monkeypatch):
    from panel import app as app_mod, botctl
    monkeypatch.setattr(botctl, "is_running", lambda: True)
    resp = app_mod.app.test_client().post(
        "/api/uninstall/remove", json={"paths": [], "clearData": True},
        headers={"Origin": "http://127.0.0.1:8765"})
    assert resp.get_json()["ok"] is False                  # bot 在跑 → 擋下（模型/檔案可能在用）


def test_legacy_libreoffice_refused_never_runs_brew(monkeypatch, tmp_path):
    _tmp_manifest(monkeypatch, tmp_path)
    lo = tmp_path / "LibreOffice.app"
    lo.mkdir()
    monkeypatch.setattr(uninstall, "_legacy_candidates",
                        lambda: [{"kind": "libreoffice", "path": str(lo), "method": "brew-cask", "legacy": True}])
    called = []
    monkeypatch.setattr(uninstall.subprocess, "run", lambda *a, **k: called.append(a))
    r = uninstall.remove([str(lo)], clear_data=False)
    assert r["results"][0]["ok"] is False                  # 來源不明 → 拒絕
    assert lo.exists()                                      # 沒刪掉使用者的 LibreOffice
    assert called == []                                     # 絕不跑 brew uninstall


def test_chromium_only_subdir_never_touches_root_or_siblings(monkeypatch, tmp_path):
    _tmp_manifest(monkeypatch, tmp_path)
    root = tmp_path / "ms-playwright"
    root.mkdir()
    sub = root / "chromium-1234"; sub.mkdir(); (sub / "x").write_text("a", encoding="utf-8")
    firefox = root / "firefox-9"; firefox.mkdir(); (firefox / "y").write_text("b", encoding="utf-8")
    monkeypatch.setattr(install_manifest, "playwright_browsers_dir", lambda: root)
    monkeypatch.setattr(uninstall, "_legacy_candidates",
                        lambda: [{"kind": "chromium", "path": str(sub), "method": "playwright", "legacy": True}])
    r = uninstall.remove([str(sub)], clear_data=False)
    assert r["results"][0]["ok"] is True
    assert not sub.exists()                                 # 只刪 JAYVIS 的 chromium 子目錄
    assert firefox.exists()                                 # 別工具的 firefox 不動
    assert root.exists()                                    # 共用根目錄不動


def test_chromium_rejects_root_path(monkeypatch, tmp_path):
    _tmp_manifest(monkeypatch, tmp_path)
    root = tmp_path / "ms-playwright"
    root.mkdir(); (root / "keep").write_text("z", encoding="utf-8")
    monkeypatch.setattr(install_manifest, "playwright_browsers_dir", lambda: root)
    monkeypatch.setattr(install_manifest, "items",
                        lambda: [{"kind": "chromium", "path": str(root), "method": "playwright"}])
    r = uninstall.remove([str(root)], clear_data=False)
    assert r["results"][0]["ok"] is False                   # 餵根目錄 → 拒絕（只准子目錄）
    assert root.exists()                                    # 共用根完好


def test_residual_keeps_manifest_entry(monkeypatch, tmp_path):
    _tmp_manifest(monkeypatch, tmp_path)
    target = tmp_path / "m"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    install_manifest.record("model", str(target), name="m")
    monkeypatch.setattr(uninstall.shutil, "rmtree", lambda *a, **k: None)  # 模擬刪不掉（被占用/權限）
    r = uninstall.remove([str(target)], clear_data=False)
    assert r["results"][0]["ok"] is False                   # 還在 → 不算成功
    assert install_manifest.items()                         # manifest 保留該筆供重試，不會誤 forget


def test_quit_endpoint_returns_ok_and_schedules_close(monkeypatch):
    from panel import app as app_mod
    scheduled = []
    class _FakeTimer:                                       # 不真的關窗，只記錄有排程
        def __init__(self, delay, fn): scheduled.append((delay, fn))
        def start(self): pass
    monkeypatch.setattr(app_mod.threading, "Timer", _FakeTimer)
    resp = app_mod.app.test_client().post(
        "/api/quit", json={}, headers={"Origin": "http://127.0.0.1:8765"})
    assert resp.get_json()["ok"] is True
    assert scheduled and scheduled[0][0] > 0                # 延遲後才關（先送出回應）


def test_clear_data_suspends_browser_watchdog(monkeypatch, tmp_path):
    import browse_launch
    data = tmp_path / "ndir"; data.mkdir(); (data / "kb.sqlite").write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr(install_manifest, "MANIFEST", data / "installed.json")
    calls = []
    monkeypatch.setattr(browse_launch, "suspend_watchdog", lambda: calls.append("suspend"))
    monkeypatch.setattr(browse_launch, "shutdown", lambda: calls.append("shutdown"))
    monkeypatch.setattr(browse_launch, "resume_watchdog", lambda: calls.append("resume"))
    uninstall.remove([], clear_data=True)
    assert calls == ["suspend", "shutdown", "resume"]       # 先暫停看門狗→收瀏覽器→（刪）→復原
    assert not (data / "kb.sqlite").exists()
