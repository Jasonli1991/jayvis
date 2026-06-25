import group_memory


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(group_memory, "GROUP_PATH", tmp_path / "group.json")


def test_record_and_transcript(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    group_memory.record(123, "Alice", "錢包功能進度?")
    group_memory.record(123, "Bob", "等廠商審核")
    t = group_memory.recent_transcript(123)
    assert t == "Alice：錢包功能進度?\nBob：等廠商審核"


def test_caps_at_max(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for i in range(25):
        group_memory.record(1, f"U{i}", f"msg{i}")
    lines = group_memory.recent_transcript(1).splitlines()
    assert len(lines) == group_memory.MAX_MSGS == 20
    assert lines[0] == "U5：msg5" and lines[-1] == "U24：msg24"   # 只剩最後 20 則


def test_per_chat_isolation(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    group_memory.record(1, "A", "g1")
    group_memory.record(2, "B", "g2")
    assert group_memory.recent_transcript(1) == "A：g1"
    assert group_memory.recent_transcript(2) == "B：g2"


def test_text_truncated(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    group_memory.record(1, "A", "x" * 1000)
    line = group_memory.recent_transcript(1)
    assert len(line) <= len("A：") + group_memory.MAX_TEXT + 1   # +省略號容忍


def test_persists_across_reload(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    group_memory.record(9, "A", "持久測試")
    assert "持久測試" in group_memory.recent_transcript(9)   # 重讀檔仍在


def test_empty_chat_returns_empty(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert group_memory.recent_transcript(999) == ""


def test_clear(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    group_memory.record(1, "A", "x")
    group_memory.clear(1)
    assert group_memory.recent_transcript(1) == ""
