from db.connection import get_conn, apply_schema
from chunks import ChunkRecord, upsert_chunk
from retrieval.orchestrator import answer_context


def test_answer_context_excludes_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("RETRIEVAL_THRESHOLD", "0.0")   # 不 abstain，看回什麼
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    upsert_chunk(conn, ChunkRecord(id="c1", source_type="conversation", raw_text="某人說的私訊秘密東京", speaker="100"))
    upsert_chunk(conn, ChunkRecord(id="d1", source_type="obsidian", raw_text="東京專案文件", doc_path="x.md"))
    res = answer_context(conn, "東京")
    assert "conversation" not in res.source_types     # 文件 RAG 不撈記憶
