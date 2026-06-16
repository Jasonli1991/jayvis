from db.connection import get_conn, apply_schema


def _db(tmp_path):
    c = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(c)
    return c


def test_schema_has_note_meta_and_links(tmp_path):
    c = _db(tmp_path)
    c.execute("INSERT INTO note_meta (doc_path, title, is_moc) VALUES ('a.md','A',1)")
    c.execute("INSERT INTO note_links (src, dst) VALUES ('a.md','b.md')")
    assert c.execute("SELECT is_moc FROM note_meta WHERE doc_path='a.md'").fetchone()["is_moc"] == 1
    assert c.execute("SELECT dst FROM note_links WHERE src='a.md'").fetchone()["dst"] == "b.md"


import obsidian_graph


def test_neighbors_out_in_and_moc_first(tmp_path):
    c = _db(tmp_path)
    c.executemany("INSERT INTO note_meta (doc_path,title,is_moc) VALUES (?,?,?)",
                  [("A.md", "A", 0), ("B.md", "B", 1), ("C.md", "C", 0)])
    c.executemany("INSERT INTO note_links (src,dst) VALUES (?,?)",
                  [("A.md", "B.md"), ("C.md", "A.md")])   # A 出鏈 B、入鏈 C
    nbs = obsidian_graph.neighbors(c, ["A.md"])
    assert set(nbs) == {"B.md", "C.md"}        # 出+入鏈都算
    assert nbs[0] == "B.md"                     # MOC 排前
    assert "A.md" not in nbs                     # 排除自己


def test_neighbors_respects_max(tmp_path):
    c = _db(tmp_path)
    c.executemany("INSERT INTO note_meta (doc_path,title,is_moc) VALUES (?,?,0)",
                  [("A.md", "A"), ("B.md", "B"), ("C.md", "C"), ("D.md", "D")])
    c.executemany("INSERT INTO note_links (src,dst) VALUES (?,?)",
                  [("A.md", "B.md"), ("A.md", "C.md"), ("A.md", "D.md")])
    assert len(obsidian_graph.neighbors(c, ["A.md"], max_notes=2)) == 2


def test_expand_context_builds_block_with_excerpt(tmp_path):
    c = _db(tmp_path)
    c.execute("INSERT INTO note_meta (doc_path,title,is_moc) VALUES ('B.md','B筆記',1)")
    c.execute("INSERT INTO note_links (src,dst) VALUES ('A.md','B.md')")
    c.execute("INSERT INTO chunks (id,source_type,owner,doc_path,raw_text,content_hash) "
              "VALUES ('obsidian::B.md::0::0','obsidian','owner','B.md','B 的內容節錄','h1')")
    out = obsidian_graph.expand_context(c, ["A.md"])
    assert "相關筆記" in out
    assert "[[B筆記]]" in out and "B.md" in out
    assert "B 的內容節錄" in out


def test_expand_context_no_neighbors_returns_empty(tmp_path):
    c = _db(tmp_path)
    c.execute("INSERT INTO note_meta (doc_path,title,is_moc) VALUES ('A.md','A',0)")
    assert obsidian_graph.expand_context(c, ["A.md"]) == ""


from types import SimpleNamespace

from retrieval import orchestrator


def _fake_decision():
    cand = SimpleNamespace(source_type="obsidian", raw_text="主題內容", meta={"doc_path": "A.md"})
    scored = SimpleNamespace(cand=cand)
    return SimpleNamespace(abstain=False, top=[scored], reason="ok"), scored


def test_answer_context_appends_graph_when_enabled(monkeypatch):
    decision, scored = _fake_decision()
    monkeypatch.setattr(orchestrator, "hybrid_search", lambda *a, **k: [])
    monkeypatch.setattr(orchestrator, "rerank", lambda *a, **k: [scored])
    monkeypatch.setattr(orchestrator, "decide", lambda *a, **k: decision)
    monkeypatch.setattr(orchestrator.obsidian_graph, "expand_context",
                        lambda conn, paths, **k: "## 相關筆記（沿你的雙鏈擴展）\n- [[B]]（B.md）\n  節錄")
    res_on = orchestrator.answer_context(None, "問題", expand_graph=True)
    assert "相關筆記" in res_on.context and "[[B]]" in res_on.context
    res_off = orchestrator.answer_context(None, "問題", expand_graph=False)
    assert "相關筆記" not in res_off.context
