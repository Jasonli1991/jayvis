from datetime import datetime

import agent
import config


def test_execute_records_action(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 999)
    recorded = []
    monkeypatch.setattr(agent.memory, "append",
                        lambda pid, kind, content, **k: recorded.append((pid, kind, content)))
    monkeypatch.setattr(agent.mail, "send_mail", lambda *a, **k: {"sent": True})
    out = agent._execute({"action": "send_email", "intent": {"to": "a@b.com"}, "account": ""})
    assert "寄出" in out
    assert recorded and recorded[0][1] == "action" and "寄出" in recorded[0][2]


def test_handle_media_records_media(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 999)
    recorded = []
    monkeypatch.setattr(agent.memory, "append",
                        lambda pid, kind, content, **k: recorded.append((kind, content)))
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"remove_bg"}')
    monkeypatch.setattr(agent.image_tool, "remove_background", lambda b: b"\x89PNG")
    r = agent.handle_media("去背", b"img", "cat.png", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"\x89PNG"
    assert recorded and recorded[0][0] == "media"
