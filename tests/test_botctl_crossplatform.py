"""botctl 跨平台行程探活／終止的測試。

macOS/Linux 用 os.kill(pid,0) 探活、SIGTERM/SIGKILL 終止；Windows 沒有這些語意
（os.kill(pid,0) 在 Windows 會直接終止行程），改用 tasklist／taskkill。
這裡在 macOS 上用 monkeypatch 模擬 _IS_WIN，驗證 Windows 分支組出的指令正確。
"""
from panel import botctl


def test_terminate_windows_uses_taskkill(monkeypatch):
    calls = []
    monkeypatch.setattr(botctl, "_IS_WIN", True)
    monkeypatch.setattr(botctl.subprocess, "run", lambda args, **k: calls.append(args))
    botctl._terminate(1234, force=False)
    botctl._terminate(1234, force=True)
    assert calls[0] == ["taskkill", "/PID", "1234"]          # 優雅
    assert calls[1] == ["taskkill", "/PID", "1234", "/F"]    # 強制


def test_terminate_unix_uses_signals(monkeypatch):
    import signal
    sent = []
    monkeypatch.setattr(botctl, "_IS_WIN", False)
    monkeypatch.setattr(botctl.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    botctl._terminate(1234, force=False)
    botctl._terminate(1234, force=True)
    assert sent == [(1234, signal.SIGTERM), (1234, signal.SIGKILL)]


def test_pid_alive_windows_parses_tasklist(monkeypatch):
    monkeypatch.setattr(botctl, "_IS_WIN", True)

    class _R:
        def __init__(self, out): self.stdout = out
    monkeypatch.setattr(botctl.subprocess, "run",
                        lambda *a, **k: _R("python.exe                   1234 Console   1   120,000 K"))
    assert botctl._pid_alive(1234) is True
    monkeypatch.setattr(botctl.subprocess, "run",
                        lambda *a, **k: _R("INFO: No tasks are running which match the specified criteria."))
    assert botctl._pid_alive(9999) is False
