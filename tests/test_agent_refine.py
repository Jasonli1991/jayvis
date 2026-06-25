from datetime import datetime

import pytest

import agent
import config
import calendar_tool as cal


def _now():
    return datetime(2026, 6, 11)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    agent.reset()
    monkeypatch.setattr(cal, "list_calendars", lambda: [])
    monkeypatch.setattr(cal, "create_event",
                        lambda title, start, end, notes="", calendar=None, all_day=False: {"uid": "X"})


def test_create_correction_refines_not_cancel(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "家人共享")
    gen = {"r": '{"action":"create","title":"台北出差","start":"2026-07-15","end":"2026-07-15","all_day":true,"notes":""}'}
    monkeypatch.setattr(agent.llm, "generate", lambda **k: gen["r"])
    out1 = agent.handle("7/15 台北出差", _now())
    assert "整天" in out1 and "7/15" in out1
    gen["r"] = '{"start":"2026-07-15","end":"2026-07-16","all_day":true}'   # 補正：延到 7/16
    out2 = agent.handle("7/16也是哦", _now())
    assert "取消了" not in out2
    assert "7/16" in out2 and "整天" in out2            # 重新確認、含 7/16


def test_create_cancel_word_cancels(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "工作")
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"create","title":"開會","start":"2026-07-15T10:00","end":"2026-07-15T11:00","notes":""}')
    agent.handle("7/15 十點開會", _now())
    assert "取消" in agent.handle("取消", _now())


def test_create_refine_unparseable_keeps_pending(monkeypatch):
    monkeypatch.setattr(config, "CALENDAR_NAME", "工作")
    gen = {"r": '{"action":"create","title":"開會","start":"2026-07-15T10:00","end":"2026-07-15T11:00","notes":""}'}
    monkeypatch.setattr(agent.llm, "generate", lambda **k: gen["r"])
    agent.handle("7/15 十點開會", _now())
    gen["r"] = "我看不懂"                                # 非 JSON → 解讀失敗
    out = agent.handle("欸那個", _now())
    assert "沒抓到" in out
    out2 = agent.handle("yes", _now())                  # pending 仍在 → yes 執行原草稿
    assert "排好" in out2


def test_update_correction_refines(monkeypatch):
    gen = {"r": '{"action":"update","match":{"title":"開會","date":"2026-06-15"},"changes":{"start":"2026-06-18T14:00","end":"2026-06-18T15:00"}}'}
    monkeypatch.setattr(agent.llm, "generate", lambda **k: gen["r"])
    monkeypatch.setattr(cal, "list_events", lambda s, e, calendar=None: [
        {"uid": "U1", "title": "與 Max 開會", "start": "2026-06-15T15:00", "end": "2026-06-15T16:00"}])
    out1 = agent.handle("把 6/15 開會改到 18 號下午兩點", _now())
    assert "yes" in out1.lower()
    gen["r"] = '{"action":"update","match":{"title":"開會","date":"2026-06-15"},"changes":{"start":"2026-06-18T20:00","end":"2026-06-18T21:00"}}'
    out2 = agent.handle("改晚上8點", _now())                  # 非 yes/取消 → 重新解讀
    assert "取消了" not in out2 and "yes" in out2.lower()


def test_delete_correction_refines(monkeypatch):
    gen = {"r": '{"action":"delete","match":{"title":"Max","date":"2026-06-15"}}'}
    monkeypatch.setattr(agent.llm, "generate", lambda **k: gen["r"])
    monkeypatch.setattr(cal, "list_events", lambda s, e, calendar=None: [
        {"uid": "U1", "title": "與 Max 開會", "start": "2026-06-15T15:00", "end": "2026-06-15T16:00"}])
    out1 = agent.handle("刪 6/15 跟 Max 的會", _now())
    assert "yes" in out1.lower()
    out2 = agent.handle("再幫我確認一下", _now())              # 非 yes/取消 → 重新比對重新確認
    assert "取消了" not in out2 and "yes" in out2.lower()
