import panel.botctl as botctl


def _tmp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(botctl, "PID_FILE", tmp_path / ".bot.pid")
    monkeypatch.setattr(botctl, "LOG_FILE", tmp_path / "bot.log")


def test_not_running_without_pid(tmp_path, monkeypatch):
    _tmp_paths(tmp_path, monkeypatch)
    assert botctl.is_running() is False


def test_tail_log(tmp_path, monkeypatch):
    _tmp_paths(tmp_path, monkeypatch)
    (tmp_path / "bot.log").write_text("a\nb\nc\nd\n", encoding="utf-8")
    assert botctl.tail_log(2) == "c\nd"


def test_start_noop_when_running(tmp_path, monkeypatch):
    _tmp_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(botctl, "is_running", lambda: True)
    called = {"n": 0}
    monkeypatch.setattr(botctl.subprocess, "Popen",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    botctl.start()
    assert called["n"] == 0  # 已在跑 → 不重複啟動
