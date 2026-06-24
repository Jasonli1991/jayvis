"""行事曆清單去重的回歸測試。

複現問題：開機預熱（warm_calendars）與第一則訊息的 _writable_calendars() 並發，兩者都看到快取空、
各抓一次（list_calendars 抓遠端日曆慢 ~22s，視窗大）→ 快取被 extend 兩次 → 清單重複（1-11 又 12-22）。
修法：calendar_tool.list_calendars 去重；agent._writable_calendars 加鎖＋雙重檢查＋去重，只填一次。
"""
import datetime

import agent
import calendar_tool


def test_build_system_warns_against_fake_meet_links():
    s = agent.build_system(datetime.datetime(2026, 6, 26, 15, 0), calendar_on=True)
    assert "meet.google.com/new" in s and "編造會議連結" in s   # 提示 LLM 別自塞通用 Meet 連結


def test_list_calendars_dedupes(monkeypatch):
    monkeypatch.setattr(calendar_tool, "_run",
                        lambda script, timeout=20: "居家\nT-EX\n居家\n工作\nT-EX\n")
    assert calendar_tool.list_calendars() == ["居家", "T-EX", "工作"]


def test_writable_calendars_dedupes_and_fetches_once(monkeypatch):
    agent._calendars_cache.clear()
    calls = []

    def fake_list():
        calls.append(1)
        return ["居家", "工作", "居家"]      # 帶重複

    monkeypatch.setattr(agent.cal, "list_calendars", fake_list)
    try:
        assert agent._writable_calendars() == ["居家", "工作"]   # 去重
        assert agent._writable_calendars() == ["居家", "工作"]   # 第二次用快取
        assert len(calls) == 1                                    # 只抓一次（不會重複 extend）
    finally:
        agent._calendars_cache.clear()                            # 還原，避免污染其他測試
