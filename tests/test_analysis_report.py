import analysis


def test_clean_html_strips_fences():
    assert analysis._clean_html("```html\n<html></html>\n```") == "<html></html>"
    assert analysis._clean_html("```\n<html></html>\n```") == "<html></html>"
    assert analysis._clean_html("<html></html>") == "<html></html>"


def test_looks_like_html():
    assert analysis._looks_like_html("<!DOCTYPE html><html>") is True
    assert analysis._looks_like_html("<canvas id=x></canvas>") is True
    assert analysis._looks_like_html("just plain text") is False


def test_inject_chartjs_after_head(monkeypatch):
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    out = analysis._inject_chartjs("<html><head><title>x</title></head><body></body></html>")
    assert "<head><script>/*CJS*/</script>" in out


def test_inject_chartjs_no_head(monkeypatch):
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    out = analysis._inject_chartjs("<html><body></body></html>")
    assert out.startswith("<html><script>/*CJS*/</script>")


def test_inject_chartjs_no_html_tag(monkeypatch):
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    out = analysis._inject_chartjs("<canvas></canvas>")
    assert out.startswith("<script>/*CJS*/</script>")


import config
from datetime import datetime


class _Cand:
    source_type = "obsidian"
    meta = {}
    raw_text = "一些知識庫資料片段"


def _patch_retrieval(monkeypatch, cands):
    monkeypatch.setattr(analysis, "_open_conn", lambda: None)
    monkeypatch.setattr(analysis, "hybrid_search", lambda conn, q, owner=None, out_k=40: cands)
    monkeypatch.setattr(analysis, "_source_label", lambda c: "note:x")


def test_generate_report_failfast_no_vault(monkeypatch):
    monkeypatch.setattr(config, "OBSIDIAN_PATH", "")
    gen = {"n": 0}
    monkeypatch.setattr(analysis, "generate", lambda **k: gen.__setitem__("n", 1) or "<html></html>")
    r = analysis.generate_report("分析X")
    assert r["ok"] is False and "路徑" in r["error"]
    assert gen["n"] == 0                                  # fail-fast：模型未被呼叫


def test_generate_report_writes_html_to_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(tmp_path))
    _patch_retrieval(monkeypatch, [_Cand()])
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    monkeypatch.setattr(analysis, "generate",
                        lambda **k: "<!DOCTYPE html><html><head></head><body><canvas></canvas></body></html>")
    r = analysis.generate_report("我的分析", now=datetime(2026, 6, 18, 15, 30))
    assert r["ok"] is True
    assert r["filename"].endswith(".html") and "analysis" in r["filename"]
    assert not r["path"].endswith(".md")
    assert "00_Raw/Inbox" in r["path"].replace("\\", "/")
    written = open(r["path"], encoding="utf-8").read()
    assert "/*CJS*/" in written and "<canvas>" in written  # 注入了 Chart.js、含模型內容


def test_generate_report_non_html_retries_then_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(tmp_path))
    _patch_retrieval(monkeypatch, [_Cand()])
    calls = {"n": 0}
    monkeypatch.setattr(analysis, "generate",
                        lambda **k: calls.__setitem__("n", calls["n"] + 1) or "抱歉，這不是 HTML")
    r = analysis.generate_report("X")
    assert r["ok"] is False and calls["n"] == 2           # 重試一次後仍失敗


def test_generate_report_no_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(tmp_path))
    _patch_retrieval(monkeypatch, [])
    r = analysis.generate_report("X")
    assert r["ok"] is False and "找不到" in r["error"]
