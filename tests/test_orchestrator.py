from chunks import ChunkRecord, upsert_chunk
from retrieval.orchestrator import answer_context


def test_abstain_on_empty_db(conn):
    r = answer_context(conn, "完全不存在的問題 xyzzy")
    assert r.abstain is True
    assert r.context == ""


def test_answer_with_citation(conn):
    upsert_chunk(conn, ChunkRecord(
        id="obsidian::projy::0", source_type="obsidian",
        doc_path="02_Outputs/Projects/projy.md",
        raw_text="projy 在 2026 改用 pgvector 取代 Chroma，因為要混合檢索。"))
    r = answer_context(conn, "projy 為什麼改用 pgvector")
    assert r.abstain is False
    assert "pgvector" in r.context
    assert any("projy.md" in c for c in r.citations)
    assert r.source_types == ["obsidian"]
