from datetime import datetime

import agent
import doc_tool
import image_tool


# ── Task 6: 意圖解析 + media prompt ─────────────────────────────────────────

def test_parse_media_intent_actions():
    assert agent.parse_media_intent('{"action":"remove_bg"}')["action"] == "remove_bg"
    assert agent.parse_media_intent('{"action":"convert","to":"pdf"}')["to"] == "pdf"
    r = agent.parse_media_intent('{"action":"resize","width":1080,"dpi":300}')
    assert r["action"] == "resize" and r["width"] == 1080 and r["dpi"] == 300


def test_parse_media_intent_rejects_non_media():
    assert agent.parse_media_intent('{"action":"create","title":"x"}') is None
    assert agent.parse_media_intent("隨便聊天") is None


def test_build_media_system_lists_three_actions():
    s = agent.build_media_system(datetime(2026, 6, 12, 9, 0))
    assert "remove_bg" in s and "convert" in s and "resize" in s
    assert "send_email" not in s and "create" not in s


# ── Task 7: handle_media 分派 ───────────────────────────────────────────────

def test_handle_media_remove_bg(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"remove_bg"}')
    monkeypatch.setattr(image_tool, "remove_background", lambda b: b"\x89PNG_nobg")
    r = agent.handle_media("幫我去背", b"rawjpg", "cat.jpg", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"\x89PNG_nobg"
    assert r.filename.endswith(".png")


def test_handle_media_convert_image_to_pdf(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"convert","to":"pdf"}')
    monkeypatch.setattr(image_tool, "convert_image", lambda b, s, t: b"%PDF-fake")
    r = agent.handle_media("轉成pdf", b"img", "p.png", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"%PDF-fake" and r.filename == "p.pdf"


def test_handle_media_convert_document_routes_to_doc_tool(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"convert","to":"pdf"}')
    monkeypatch.setattr(doc_tool, "convert_document", lambda b, s, t: b"%PDF-doc")
    r = agent.handle_media("轉pdf", b"docxbytes", "report.docx", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"%PDF-doc" and r.filename == "report.pdf"


def test_handle_media_resize(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"resize","width":1080,"dpi":300}')
    seen = {}
    def fake_resize(b, s, **kw):
        seen.update(kw)
        return b"resized"
    monkeypatch.setattr(image_tool, "resize_image", fake_resize)
    r = agent.handle_media("縮到1080並改300dpi", b"img", "a.jpg", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"resized"
    assert seen.get("width") == 1080 and seen.get("dpi") == 300


def test_handle_media_unsupported_conversion(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"convert","to":"docx"}')
    r = agent.handle_media("把圖轉docx", b"img", "a.png", datetime(2026, 6, 12, 9, 0))
    assert r.file is None and "做不到" in r.message


def test_handle_media_quota(monkeypatch):
    def boom(**k):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(agent.llm, "generate", boom)
    r = agent.handle_media("去背", b"img", "a.png", datetime(2026, 6, 12, 9, 0))
    assert r.file is None and r.message == agent._QUOTA_MSG


def test_handle_media_soffice_missing(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"convert","to":"pdf"}')
    def raise_missing(b, s, t):
        raise doc_tool.SofficeMissing()
    monkeypatch.setattr(doc_tool, "convert_document", raise_missing)
    r = agent.handle_media("轉pdf", b"d", "r.docx", datetime(2026, 6, 12, 9, 0))
    assert r.file is None and "LibreOffice" in r.message


# ── 成功回傳要有說明（resize/convert 不能只剩壓縮警告）─────────────────────────

def test_resize_has_success_note(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate",
                        lambda **k: '{"action":"resize","width":800,"height":800}')
    monkeypatch.setattr(image_tool, "resize_image", lambda b, s, **kw: b"resized")
    r = agent.handle_media("調整成800x800", b"img", "a.jpg", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"resized" and r.note


def test_convert_has_success_note(monkeypatch):
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"convert","to":"pdf"}')
    monkeypatch.setattr(image_tool, "convert_image", lambda b, s, t: b"%PDF-x")
    r = agent.handle_media("轉pdf", b"img", "a.png", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"%PDF-x" and r.note


# ── 記住上一張圖 + 純文字跟進 ───────────────────────────────────────────────

def test_looks_like_media_request():
    assert agent.looks_like_media_request("幫我去背")
    assert agent.looks_like_media_request("縮到 800")
    assert agent.looks_like_media_request("改成 300dpi")
    assert agent.looks_like_media_request("轉成 pdf")
    assert not agent.looks_like_media_request("明天下午三點跟 Max 開會")
    assert not agent.looks_like_media_request("把這封轉介給 Sam")


def test_remember_and_followup(monkeypatch):
    agent.reset()
    assert agent.has_remembered_media() is False
    agent.remember_media(b"IMG", "cat.png")
    assert agent.has_remembered_media() is True
    monkeypatch.setattr(agent.llm, "generate", lambda **k: '{"action":"remove_bg"}')
    monkeypatch.setattr(image_tool, "remove_background",
                        lambda b: b"\x89PNGnobg" if b == b"IMG" else b"WRONG")
    r = agent.handle_media_followup("去背", datetime(2026, 6, 12, 9, 0))
    assert r.file == b"\x89PNGnobg" and r.filename == "cat-nobg.png"


def test_followup_without_image():
    agent.reset()
    r = agent.handle_media_followup("去背", datetime(2026, 6, 12, 9, 0))
    assert r.file is None and "傳" in r.message


def test_reset_clears_remembered_media():
    agent.remember_media(b"X", "a.png")
    agent.reset()
    assert agent.has_remembered_media() is False
