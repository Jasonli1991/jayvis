from db.connection import get_conn, apply_schema
from chunks import ChunkRecord, upsert_chunk
from retrieval.hybrid import hybrid_search


def _seed(conn):
    upsert_chunk(conn, ChunkRecord(id="d1", source_type="obsidian", raw_text="專案 Falcon 的設計文件", doc_path="x.md"))
    upsert_chunk(conn, ChunkRecord(id="c1", source_type="conversation", raw_text="我下週要去東京出差", speaker="100"))
    upsert_chunk(conn, ChunkRecord(id="c2", source_type="conversation", raw_text="我下週要去東京出差", speaker="200"))


def test_exclude_source_types(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    _seed(conn)
    got = hybrid_search(conn, "東京出差", out_k=10, exclude_source_types=("conversation", "action"))
    assert all(c.source_type != "conversation" for c in got)


def test_speaker_scope(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    _seed(conn)
    got = hybrid_search(conn, "東京出差", out_k=10, source_types=("conversation",), speaker="100")
    ids = {c.id for c in got}
    assert "c1" in ids and "c2" not in ids       # 只回想 speaker=100 的
