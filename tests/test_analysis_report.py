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


def test_version_filename():
    assert analysis._version_filename("2026-x-analysis-y", 1) == "2026-x-analysis-y.html"
    assert analysis._version_filename("2026-x-analysis-y", 2) == "2026-x-analysis-y-v2.html"
    assert analysis._version_filename("2026-x-analysis-y", 3) == "2026-x-analysis-y-v3.html"


def test_generate_report_remembers_last(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(tmp_path))
    _patch_retrieval(monkeypatch, [_Cand()])
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    monkeypatch.setattr(analysis, "generate",
                        lambda **k: "<html><head></head><body><canvas></canvas></body></html>")
    analysis._last_report = None
    r = analysis.generate_report("我的分析", now=datetime(2026, 6, 22, 15, 30))
    assert r["ok"] is True
    lr = analysis._last_report
    assert lr["version"] == 1
    assert "/*CJS*/" not in lr["clean_html"]      # 記的是注入 Chart.js 之前的乾淨 HTML
    assert "<canvas>" in lr["clean_html"]
    assert lr["stem"] == r["filename"][:-5]        # stem = 檔名去掉 .html


def test_refine_no_last_report(monkeypatch):
    analysis._last_report = None
    gen = {"n": 0}
    monkeypatch.setattr(analysis, "generate", lambda **k: gen.__setitem__("n", 1) or "<html></html>")
    r = analysis.refine_report("改成長條圖")
    assert r["ok"] is False and "先執行" in r["error"]
    assert gen["n"] == 0


def test_refine_failfast_no_vault(monkeypatch):
    analysis._last_report = {"clean_html": "<html></html>", "stem": "x-analysis-y", "version": 1}
    monkeypatch.setattr(config, "OBSIDIAN_PATH", "")
    gen = {"n": 0}
    monkeypatch.setattr(analysis, "generate", lambda **k: gen.__setitem__("n", 1) or "<html></html>")
    r = analysis.refine_report("改")
    assert r["ok"] is False and "路徑" in r["error"]
    assert gen["n"] == 0


def test_refine_writes_new_version(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(tmp_path))
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    analysis._last_report = {"clean_html": "<html><body>原始內容</body></html>",
                             "stem": "2026-x-analysis-y", "version": 1}
    seen = {}
    monkeypatch.setattr(analysis, "generate",
                        lambda **k: seen.update(user=k["messages"][0]["content"])
                        or "<html><body><canvas></canvas>改好了</body></html>")
    r = analysis.refine_report("第二張圖改長條圖", now=datetime(2026, 6, 22, 16, 0))
    assert r["ok"] is True
    assert r["filename"] == "2026-x-analysis-y-v2.html"
    assert "原始內容" in seen["user"] and "第二張圖改長條圖" in seen["user"]
    assert analysis._last_report["version"] == 2
    written = open(r["path"], encoding="utf-8").read()
    assert "/*CJS*/" in written and "改好了" in written


def test_refine_non_html_retries_then_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(tmp_path))
    analysis._last_report = {"clean_html": "<html></html>", "stem": "s", "version": 1}
    calls = {"n": 0}
    monkeypatch.setattr(analysis, "generate",
                        lambda **k: calls.__setitem__("n", calls["n"] + 1) or "這不是HTML")
    r = analysis.refine_report("改")
    assert r["ok"] is False and calls["n"] == 2
