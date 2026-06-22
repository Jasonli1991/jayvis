from datetime import datetime

import config
import leave_digest


def _leave(start, end):
    return {"leave_start": start, "leave_end": end, "status": "", "focus": ""}


def test_compile_failfast_no_leave(monkeypatch):
    monkeypatch.setattr(leave_digest.env_io, "read_leave", lambda: _leave("", ""))
    gen = {"n": 0}
    monkeypatch.setattr(leave_digest, "generate", lambda **k: gen.__setitem__("n", 1) or "x")
    r = leave_digest.compile_digest()
    assert r["ok"] is False and "請假期間" in r["error"] and gen["n"] == 0   # 不碰 LLM


def test_compile_no_records(monkeypatch):
    monkeypatch.setattr(leave_digest.env_io, "read_leave", lambda: _leave("2026-06-20", "2026-06-25"))
    monkeypatch.setattr(leave_digest.memory, "conversations_between", lambda *a, **k: [])
    gen = {"n": 0}
    monkeypatch.setattr(leave_digest, "generate", lambda **k: gen.__setitem__("n", 1) or "x")
    r = leave_digest.compile_digest()
    assert r["ok"] is False and "沒有同事互動" in r["error"] and gen["n"] == 0


def test_compile_ok(monkeypatch):
    monkeypatch.setattr(leave_digest.env_io, "read_leave", lambda: _leave("2026-06-20", "2026-06-25"))
    rows = [{"ts": "2026-06-21 10:00:00", "person_alias": "Alice", "person_id": "111",
             "kind": "user", "content": "幫我問X進度"}]
    monkeypatch.setattr(leave_digest.memory, "conversations_between",
                        lambda start, end, exclude_person_id=None, conn=None: rows)
    seen = {}
    monkeypatch.setattr(leave_digest, "generate",
                        lambda **k: seen.update(user=k["messages"][0]["content"]) or "## 已處理的項目\n- Alice 問X")
    r = leave_digest.compile_digest()
    assert r["ok"] is True and "已處理" in r["summary"]
    assert "幫我問X進度" in seen["user"] and "Alice" in seen["user"]


def test_send_to_owner_skips_without_token(monkeypatch):
    monkeypatch.setattr(config, "TG_BOT_TOKEN", "")
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    calls = {"n": 0}
    monkeypatch.setattr(leave_digest.urllib.request, "urlopen", lambda *a, **k: calls.__setitem__("n", 1))
    assert leave_digest.send_to_owner("hi") is False and calls["n"] == 0


def test_send_to_owner_chunks_long(monkeypatch):
    monkeypatch.setattr(config, "TG_BOT_TOKEN", "T")
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    n = {"c": 0}

    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(leave_digest.urllib.request, "urlopen", lambda *a, **k: n.__setitem__("c", n["c"] + 1) or _R())
    assert leave_digest.send_to_owner("x" * 9000) is True
    assert n["c"] >= 3                        # 9000/4000 → 至少 3 段


def test_sent_marker_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(leave_digest, "_SENT_MARKER", tmp_path / "sent.txt")
    assert leave_digest._already_sent("2026-06-25") is False
    leave_digest._mark_sent("2026-06-25")
    assert leave_digest._already_sent("2026-06-25") is True
    assert leave_digest._already_sent("2026-06-30") is False    # 不同 end 視為未發


def test_check_failfast_no_leave(monkeypatch):
    monkeypatch.setattr(leave_digest.env_io, "read_leave", lambda: _leave("", ""))
    cap = {"n": 0}
    monkeypatch.setattr(leave_digest, "compile_digest", lambda **k: cap.__setitem__("n", 1) or {"ok": True})
    assert leave_digest.check_and_send() is False and cap["n"] == 0


def test_check_before_end(monkeypatch):
    monkeypatch.setattr(leave_digest.env_io, "read_leave", lambda: _leave("2026-06-20", "2026-06-25"))
    cap = {"n": 0}
    monkeypatch.setattr(leave_digest, "compile_digest", lambda **k: cap.__setitem__("n", 1) or {"ok": True})
    assert leave_digest.check_and_send(now=datetime(2026, 6, 24)) is False and cap["n"] == 0


def test_check_after_end_sends_once(tmp_path, monkeypatch):
    monkeypatch.setattr(leave_digest, "_SENT_MARKER", tmp_path / "sent.txt")
    monkeypatch.setattr(leave_digest.env_io, "read_leave", lambda: _leave("2026-06-20", "2026-06-25"))
    monkeypatch.setattr(leave_digest, "compile_digest", lambda **k: {"ok": True, "summary": "彙整內容"})
    sent = {"text": None}
    monkeypatch.setattr(leave_digest, "send_to_owner", lambda t: sent.update(text=t) or True)
    assert leave_digest.check_and_send(now=datetime(2026, 6, 26)) is True
    assert "彙整內容" in sent["text"] and leave_digest._already_sent("2026-06-25") is True
    assert leave_digest.check_and_send(now=datetime(2026, 6, 27)) is False   # 已發過不重發
