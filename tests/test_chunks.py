import numpy as np
import chunks as chunks_mod
from chunks import ChunkRecord, content_hash, upsert_chunk, citation_of
from db.connection import get_conn, apply_schema


def test_schema_creates_chunks_table(conn):
    row = conn.execute(
        "SELECT count(*) AS n FROM sqlite_master WHERE type='table' AND name='chunks'"
    ).fetchone()
    assert row["n"] == 1


def test_insert_chunk_stores_float32_blob(tmp_path, monkeypatch):
    monkeypatch.setattr(chunks_mod, "embed_texts", lambda ts: [[0.1] * 1024 for _ in ts])
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    rec = ChunkRecord(id="o::d::0", source_type="obsidian", raw_text="綠界金流串接審核", doc_path="x.md")
    assert upsert_chunk(conn, rec) is True
    assert upsert_chunk(conn, rec) is False                       # 未變則 skip
    row = conn.execute("SELECT embedding FROM chunks").fetchone()
    assert isinstance(row["embedding"], (bytes, bytearray))
    assert np.frombuffer(row["embedding"], dtype=np.float32).shape[0] == 1024
    conn.close()


def _rec(text="projy 改用 pgvector", **kw):
    base = dict(id="obsidian::doc1::0", source_type="obsidian",
                doc_path="02_Outputs/Projects/projy.md", raw_text=text)
    base.update(kw)
    return ChunkRecord(**base)


def test_content_hash_stable():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")


def test_upsert_writes_then_skips_unchanged(conn):
    rec = _rec()
    assert upsert_chunk(conn, rec) is True
    assert upsert_chunk(conn, rec) is False
    n = conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]
    assert n == 1


def test_upsert_updates_on_change(conn):
    upsert_chunk(conn, _rec(text="舊內容"))
    assert upsert_chunk(conn, _rec(text="新內容")) is True
    row = conn.execute("SELECT raw_text FROM chunks WHERE id=:id",
                       {"id": "obsidian::doc1::0"}).fetchone()
    assert row["raw_text"] == "新內容"


def test_citation_of_obsidian():
    assert "projy.md" in citation_of(_rec())
