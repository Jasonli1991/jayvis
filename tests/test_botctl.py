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


def test_owner_turns_counts_only_owner_conversation(monkeypatch):
    # logo 成長階段彩蛋訊號：只數 owner 的 user/assistant 對談（動作不算、別人不算）
    import config
    import memory
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    memory.append("6803", "user", "嗨")
    memory.append("6803", "assistant", "嗨 Jason")
    memory.append("6803", "action", "已新增會議")        # 動作不算對談
    memory.append("999", "user", "別人的訊息")            # 非 owner 不算
    assert botctl._owner_turns() == 2
    assert botctl.status()["owner_turns"] == 2


def test_owner_graduation_latches_and_survives_count_drop(tmp_path, monkeypatch):
    # 學士＝一次性畢業里程碑：曾達門檻就持久化，之後記憶整併把 count 壓回也維持學士
    monkeypatch.setattr(botctl, "_MILESTONES", tmp_path / "milestones.json")
    assert botctl._owner_graduated(50) is False        # 還沒到門檻
    assert botctl._owner_graduated(botctl._GRADUATE_AT) is True   # 達門檻 → 畢業並持久化
    assert botctl._owner_graduated(40) is True          # count 整併回落 → 仍學士（不降級）
    botctl.clear_graduation()                           # 清除全部 → 重置里程碑
    assert botctl._owner_graduated(40) is False         # 可重新成長


def test_start_noop_when_running(tmp_path, monkeypatch):
    _tmp_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(botctl, "is_running", lambda: True)
    called = {"n": 0}
    monkeypatch.setattr(botctl.subprocess, "Popen",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    botctl.start()
    assert called["n"] == 0  # 已在跑 → 不重複啟動
