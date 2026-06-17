import browse_launch as bl
import config


def test_launch_short_circuits_when_alive(monkeypatch):
    ran = []
    monkeypatch.setattr(bl, "cdp_alive", lambda timeout=1.0: True)
    monkeypatch.setattr(bl.subprocess, "run", lambda *a, **k: ran.append(a))
    assert bl.launch() is True
    assert ran == []                          # 已就緒 → 不重啟


def test_launch_opens_dedicated_profile(monkeypatch):
    monkeypatch.setattr(config, "BROWSE_CDP_URL", "http://localhost:9222")
    monkeypatch.setattr(config, "BROWSE_PROFILE_DIR", "/tmp/p")
    states = iter([False, True])              # 未就緒 → open → 就緒
    monkeypatch.setattr(bl, "cdp_alive", lambda timeout=1.0: next(states))
    cap = {}
    monkeypatch.setattr(bl.subprocess, "run", lambda args, **k: cap.update(args=args))
    assert bl.launch(wait_s=2) is True
    a = cap["args"]
    assert a[:4] == ["open", "-na", "Google Chrome", "--args"]
    assert "--remote-debugging-port=9222" in a
    assert "--user-data-dir=/tmp/p" in a      # 專用設定檔，不碰個人 Chrome


def test_shutdown_targets_dedicated_profile(monkeypatch):
    monkeypatch.setattr(config, "BROWSE_PROFILE_DIR", "/tmp/p")
    cap = {}
    monkeypatch.setattr(bl.subprocess, "run", lambda args, **k: cap.update(args=args))
    bl.shutdown()
    assert cap["args"] == ["pkill", "-f", "--user-data-dir=/tmp/p"]
