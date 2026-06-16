from chunks import ChunkRecord, upsert_chunk
import rag.retriever as r


def test_retrieve_result_abstain(conn, monkeypatch):
    monkeypatch.setattr(r, "_open_conn", lambda: conn)
    res = r.retrieve_result("不存在的問題 xyzzy")
    assert res.abstain is True


def test_retrieve_result_with_citation(conn, monkeypatch):
    monkeypatch.setattr(r, "_open_conn", lambda: conn)
    upsert_chunk(conn, ChunkRecord(id="obsidian::p::0", source_type="obsidian",
                 doc_path="projy.md", raw_text="projy 改用 pgvector 做混合檢索。"))
    res = r.retrieve_result("projy 為何用 pgvector")
    assert res.abstain is False
    assert any("projy.md" in c for c in res.citations)
