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


def test_upsert_backfills_event_time_when_unchanged(tmp_path, monkeypatch):
    # 內容沒變的 chunk 重建索引時，仍要補上 event_time（否則「近期筆記」永遠抓不到）
    monkeypatch.setattr(chunks_mod, "embed_texts", lambda ts: [[0.1] * 1024 for _ in ts])
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    rec = ChunkRecord(id="o::d::0", source_type="obsidian", raw_text="同樣內容", doc_path="x.md")
    assert upsert_chunk(conn, rec) is True                              # 首次寫入，event_time=None
    assert conn.execute("SELECT event_time FROM chunks").fetchone()["event_time"] is None
    from datetime import datetime
    rec2 = ChunkRecord(id="o::d::0", source_type="obsidian", raw_text="同樣內容",
                       doc_path="x.md", event_time=datetime(2026, 6, 10))
    assert upsert_chunk(conn, rec2) is False                            # 內容沒變仍回 False
    got = conn.execute("SELECT event_time FROM chunks").fetchone()["event_time"]
    assert got == "2026-06-10T00:00:00"                                 # 但 event_time 已被回填
    conn.close()


def test_upsert_unchanged_does_not_clear_event_time(tmp_path, monkeypatch):
    # 沒帶 event_time 的重建，不可把既有 event_time 清成 None
    monkeypatch.setattr(chunks_mod, "embed_texts", lambda ts: [[0.1] * 1024 for _ in ts])
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    from datetime import datetime
    upsert_chunk(conn, ChunkRecord(id="o::d::0", source_type="obsidian", raw_text="x",
                                   doc_path="x.md", event_time=datetime(2026, 6, 10)))
    upsert_chunk(conn, ChunkRecord(id="o::d::0", source_type="obsidian", raw_text="x", doc_path="x.md"))
    got = conn.execute("SELECT event_time FROM chunks").fetchone()["event_time"]
    assert got == "2026-06-10T00:00:00"                                 # 未被 None 清掉
    conn.close()


def test_citation_of_obsidian():
    assert "projy.md" in citation_of(_rec())
