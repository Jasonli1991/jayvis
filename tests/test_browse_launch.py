import browse_launch as bl
import config


def test_launch_short_circuits_when_alive(monkeypatch):
    ran = []
    monkeypatch.setattr(bl, "cdp_alive", lambda timeout=1.0: True)
    monkeypatch.setattr(bl.subprocess, "Popen", lambda *a, **k: ran.append(a))
    assert bl.launch() is True
    assert ran == []                          # 已就緒 → 不重啟


def test_launch_runs_bundled_chromium(monkeypatch):
    monkeypatch.setattr(config, "BROWSE_CDP_URL", "http://localhost:9222")
    monkeypatch.setattr(config, "BROWSE_PROFILE_DIR", "/tmp/p")
    monkeypatch.setattr(bl, "chromium_path", lambda: "/cache/Chromium")   # PW 自帶，非系統 Chrome
    states = iter([False, True])              # 未就緒 → 啟動 → 就緒
    monkeypatch.setattr(bl, "cdp_alive", lambda timeout=1.0: next(states))
    cap = {}
    monkeypatch.setattr(bl.subprocess, "Popen", lambda args, **k: cap.update(args=args))
    assert bl.launch(wait_s=2) is True
    a = cap["args"]
    assert a[0] == "/cache/Chromium"          # 用 bundled chromium 執行檔，不是 open -a
    assert "--remote-debugging-port=9222" in a
    assert "--user-data-dir=/tmp/p" in a
    assert "--disable-features=CalculateNativeWinOcclusion" in a   # 防遮擋時截圖卡死
    assert "--disable-gpu" in a                                    # 軟體渲染避 Metal 崩潰


def test_is_ready(monkeypatch, tmp_path):
    exe = tmp_path / "Chromium"
    exe.write_text("x")
    monkeypatch.setattr(bl, "chromium_path", lambda: str(exe))
    assert bl.is_ready() is True
    monkeypatch.setattr(bl, "chromium_path", lambda: str(tmp_path / "missing"))
    assert bl.is_ready() is False
    def boom():
        raise RuntimeError("no playwright")
    monkeypatch.setattr(bl, "chromium_path", boom)
    assert bl.is_ready() is False             # 套件沒裝 → 不崩、回 False


def test_start_install_is_background(monkeypatch, tmp_path):
    monkeypatch.setattr(bl, "INSTALL_LOG", tmp_path / "browse-install.log")
    monkeypatch.setattr(bl, "is_ready", lambda: False)
    monkeypatch.setattr(bl, "_install_proc", None)
    cap = {}
    class _P:
        def poll(self): return None            # 模擬背景仍在跑
    monkeypatch.setattr(bl.subprocess, "Popen", lambda args, **k: cap.update(args=args) or _P())
    r = bl.start_install()
    assert r == {"installing": True}           # 非阻塞、立即回
    a = cap["args"]
    assert a[0] == bl.sys.executable and a[1] == "-c"   # 背景子行程，無 shell
    assert "pip" in a[2] and "playwright" in a[2]


def test_start_install_skips_when_ready(monkeypatch):
    monkeypatch.setattr(bl, "is_ready", lambda: True)
    ran = []
    monkeypatch.setattr(bl.subprocess, "Popen", lambda *a, **k: ran.append(1))
    assert bl.start_install() == {"ready": True}
    assert ran == []                           # 已就緒 → 不重裝


def test_install_status_reports_ready_and_installing(monkeypatch):
    monkeypatch.setattr(bl, "is_ready", lambda: False)
    monkeypatch.setattr(bl, "is_installing", lambda: True)
    assert bl.install_status() == {"ready": False, "installing": True}


def test_shutdown_pattern_is_profile_path(monkeypatch):
    monkeypatch.setattr(config, "BROWSE_PROFILE_DIR", "/Users/x/.n/chrome-browse-profile")
    cap = {}
    monkeypatch.setattr(bl.subprocess, "run", lambda args, **k: cap.update(args=args))
    bl.shutdown()
    # pattern 用完整路徑、不以 - 開頭（避免 macOS pkill 把它當參數）
    assert cap["args"] == ["pkill", "-f", "/Users/x/.n/chrome-browse-profile"]
    assert not cap["args"][2].startswith("-")


def test_launch_if_enabled_off(monkeypatch):
    # 未啟用瀏覽 → 不啟動 Chrome
    monkeypatch.setattr(config, "BROWSE_ENABLED", False)
    called = {"n": 0}
    monkeypatch.setattr(bl, "launch", lambda *a, **k: called.__setitem__("n", 1) or True)
    assert bl.launch_if_enabled() is False
    assert called["n"] == 0


def test_launch_if_enabled_on(monkeypatch):
    # 啟用瀏覽 → 啟動 Chrome（啟動時重放 toggle ON 做的事）
    monkeypatch.setattr(config, "BROWSE_ENABLED", True)
    monkeypatch.setattr(bl, "launch", lambda *a, **k: True)
    assert bl.launch_if_enabled() is True


def test_launch_if_enabled_swallows_error(monkeypatch):
    # 缺 playwright/Chromium 等 → 安靜略過、不拋（面板啟用流程會引導安裝）
    monkeypatch.setattr(config, "BROWSE_ENABLED", True)
    def boom(*a, **k):
        raise RuntimeError("playwright not installed")
    monkeypatch.setattr(bl, "launch", boom)
    assert bl.launch_if_enabled() is False
