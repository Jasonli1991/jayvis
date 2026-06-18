import browse_launch
from panel import env_io
from panel import __main__ as pm


def test_watchdog_relaunches_when_enabled_and_dead(monkeypatch):
    # 啟用瀏覽 + Chrome 沒在跑（被使用者關了）→ 重開
    monkeypatch.setattr(env_io, "read_browse_enabled", lambda: True)
    monkeypatch.setattr(browse_launch, "cdp_alive", lambda timeout=1.0: False)
    called = {"n": 0}
    monkeypatch.setattr(browse_launch, "launch", lambda *a, **k: called.__setitem__("n", 1) or True)
    assert pm._browse_watchdog_tick() is True
    assert called["n"] == 1


def test_watchdog_noop_when_alive(monkeypatch):
    # Chrome 還在跑 → 不動作
    monkeypatch.setattr(env_io, "read_browse_enabled", lambda: True)
    monkeypatch.setattr(browse_launch, "cdp_alive", lambda timeout=1.0: True)
    called = {"n": 0}
    monkeypatch.setattr(browse_launch, "launch", lambda *a, **k: called.__setitem__("n", 1))
    assert pm._browse_watchdog_tick() is False
    assert called["n"] == 0


def test_watchdog_noop_when_disabled(monkeypatch):
    # 開關已關 → 別把使用者剛關掉的視窗又拉起來（讀即時 .env 狀態）
    monkeypatch.setattr(env_io, "read_browse_enabled", lambda: False)
    monkeypatch.setattr(browse_launch, "cdp_alive", lambda timeout=1.0: False)
    called = {"n": 0}
    monkeypatch.setattr(browse_launch, "launch", lambda *a, **k: called.__setitem__("n", 1))
    assert pm._browse_watchdog_tick() is False
    assert called["n"] == 0


def test_watchdog_swallows_error(monkeypatch):
    monkeypatch.setattr(env_io, "read_browse_enabled", lambda: True)
    def boom(timeout=1.0):
        raise RuntimeError("cdp check failed")
    monkeypatch.setattr(browse_launch, "cdp_alive", boom)
    assert pm._browse_watchdog_tick() is False        # 不拋


def test_watchdog_relaunches_in_login_headed_mode(monkeypatch):
    monkeypatch.setattr(env_io, "read_browse_enabled", lambda: True)
    monkeypatch.setattr(browse_launch, "cdp_alive", lambda timeout=1.0: False)
    browse_launch.set_login_mode(True)            # 登入中 → 維持 headed
    cap = {}
    monkeypatch.setattr(browse_launch, "launch", lambda headless=True, **k: cap.update(headless=headless))
    pm._browse_watchdog_tick()
    assert cap["headless"] is False
    browse_launch.set_login_mode(False)


def test_watchdog_relaunches_headless_when_not_login(monkeypatch):
    monkeypatch.setattr(env_io, "read_browse_enabled", lambda: True)
    monkeypatch.setattr(browse_launch, "cdp_alive", lambda timeout=1.0: False)
    browse_launch.set_login_mode(False)
    cap = {}
    monkeypatch.setattr(browse_launch, "launch", lambda headless=True, **k: cap.update(headless=headless))
    pm._browse_watchdog_tick()
    assert cap["headless"] is True
