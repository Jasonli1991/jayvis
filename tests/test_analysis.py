import analysis


class _C:
    def __init__(self, text, st="obsidian"):
        self.raw_text = text
        self.source_type = st
        self.meta = {"doc_path": "x.md"}


def test_analyze_synthesizes_and_returns_sources(monkeypatch):
    monkeypatch.setattr(analysis, "_open_conn", lambda: object())
    monkeypatch.setattr(analysis, "hybrid_search",
                        lambda conn, q, owner="owner", out_k=40:
                        [_C("Owner 做了 projx 競標"), _C("Max 做了 projw", "git")])
    captured = {}

    def fake_gen(model, system, messages, **kw):
        captured["model"] = model
        captured["ctx"] = messages[0]["content"]
        return "綜合分析：…"

    monkeypatch.setattr(analysis, "generate", fake_gen)
    r = analysis.analyze("職員貢獻度分析")
    assert r["answer"].startswith("綜合分析")
    assert len(r["sources"]) == 2
    assert captured["model"] == analysis.config.MODEL_CODE  # 分析用較強模型
    assert "projx" in captured["ctx"]


def test_analyze_empty(monkeypatch):
    monkeypatch.setattr(analysis, "_open_conn", lambda: object())
    monkeypatch.setattr(analysis, "hybrid_search", lambda *a, **k: [])
    r = analysis.analyze("無關問題")
    assert r["sources"] == []
