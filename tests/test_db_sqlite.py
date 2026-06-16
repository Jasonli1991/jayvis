from db.connection import get_conn, apply_schema


def test_apply_schema_and_fts_sync(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(conn)
    conn.execute(
        "INSERT INTO chunks(id, source_type, owner, raw_text, content_hash) "
        "VALUES (:id, :st, :owner, :rt, :h)",
        {"id": "a1", "st": "obsidian", "owner": "owner", "rt": "綠界金流串接審核", "h": "h1"},
    )
    rid = conn.execute("SELECT rowid FROM chunks WHERE id='a1'").fetchone()["rowid"]
    hit = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH :q",
        {"q": '"金流串接"'},
    ).fetchone()
    assert hit is not None and hit["rowid"] == rid
    conn.close()


def test_delete_clears_fts(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(conn)
    conn.execute("INSERT INTO chunks(id, source_type, raw_text, content_hash) "
                 "VALUES ('x','obsidian','錢包功能開發中','hx')")
    conn.execute("DELETE FROM chunks WHERE id='x'")
    hit = conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH :q",
                       {"q": '"錢包功能"'}).fetchone()
    assert hit is None
    conn.close()
