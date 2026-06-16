from datetime import datetime

import inbox_capture


def test_pending_remember_take():
    inbox_capture.clear()
    assert inbox_capture.has_pending() is False
    inbox_capture.remember("q1", "a1")
    assert inbox_capture.has_pending() is True
    assert inbox_capture.take() == {"q": "q1", "a": "a1"}
    assert inbox_capture.has_pending() is False


def test_is_save_command():
    assert inbox_capture.is_save_command("存")
    assert inbox_capture.is_save_command("記下來")
    assert inbox_capture.is_save_command("  YES  ")
    assert not inbox_capture.is_save_command("存一些東西給我")


def test_slug_sanitizes():
    assert inbox_capture._slug("ReAct 跟 Reflexion 差在哪？") == "ReAct-跟-Reflexion-差在哪"
    assert inbox_capture._slug("") == "note"


def test_save_to_inbox_writes_note(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox_capture.config, "OBSIDIAN_PATH", str(tmp_path))
    ok, fname = inbox_capture.save_to_inbox("ReAct 是什麼？", "ReAct 是一種…", datetime(2026, 6, 15, 18, 30))
    assert ok is True
    p = tmp_path / "00_Raw" / "Inbox" / fname
    assert p.exists()
    body = p.read_text(encoding="utf-8")
    assert "source: JAYVIS" in body
    assert "# ReAct 是什麼？" in body
    assert "ReAct 是一種…" in body
    assert fname.startswith("2026-06-15-1830-")


def test_save_to_inbox_creates_inbox_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox_capture.config, "OBSIDIAN_PATH", str(tmp_path))
    inbox_capture.save_to_inbox("q", "a", datetime(2026, 6, 15, 9, 0))
    assert (tmp_path / "00_Raw" / "Inbox").is_dir()


def test_save_to_inbox_no_path_fails_gracefully(monkeypatch):
    monkeypatch.setattr(inbox_capture.config, "OBSIDIAN_PATH", "")
    ok, msg = inbox_capture.save_to_inbox("q", "a", datetime(2026, 6, 15))
    assert ok is False and "路徑" in msg


def test_is_knowledge_question_yes(monkeypatch):
    seen = {}
    monkeypatch.setattr(inbox_capture, "generate",
                        lambda **k: seen.update(system=k["system"]) or "yes")
    assert inbox_capture.is_knowledge_question("ReAct 是什麼？") is True
    assert "知識" in seen["system"]


def test_is_knowledge_question_no(monkeypatch):
    monkeypatch.setattr(inbox_capture, "generate", lambda **k: "no")
    assert inbox_capture.is_knowledge_question("嗨") is False


def test_is_knowledge_question_empty_is_false():
    assert inbox_capture.is_knowledge_question("") is False


def test_is_knowledge_question_error_is_false(monkeypatch):
    def boom(**k):
        raise RuntimeError("quota")
    monkeypatch.setattr(inbox_capture, "generate", boom)
    assert inbox_capture.is_knowledge_question("某個概念問題") is False
