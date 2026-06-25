from db.connection import get_conn, apply_schema


def test_memories_table_exists(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
    assert {"id", "ts", "person_id", "person_alias", "kind", "content", "meta", "chunk_id"} <= cols


def test_ts_defaults_not_null(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(conn)
    conn.execute("INSERT INTO memories (id, person_id, kind, content) VALUES ('m1','7','user','hi')")
    row = conn.execute("SELECT ts FROM memories WHERE id='m1'").fetchone()
    assert row["ts"]   # 預設帶時間，非空


def test_memory_config_defaults():
    # 這些值可由使用者 .env 覆蓋（如 MEMORY_RECENT_TURNS）；驗型別/正數，不寫死值
    import config
    assert isinstance(config.MEMORY_RECENT_TURNS, int) and config.MEMORY_RECENT_TURNS > 0
    assert isinstance(config.MEMORY_RECALL_N, int) and config.MEMORY_RECALL_N > 0
    assert isinstance(config.MEMORY_MIN_CHARS, int) and config.MEMORY_MIN_CHARS > 0


import memory


def _db(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    return conn


def test_append_and_recent(tmp_path):
    conn = _db(tmp_path)
    memory.append("7", "user", "你好", alias="Eric", conn=conn)
    memory.append("7", "assistant", "嗨 Eric", alias="Eric", conn=conn)
    h = memory.recent("7", conn=conn)
    assert h == [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "嗨 Eric"}]


def test_recent_excludes_actions_and_media(tmp_path):
    # recent()（線性對話歷史）只回 user/assistant；動作/媒體不混進對話脈絡
    conn = _db(tmp_path)
    memory.append("7", "user", "幫我約明天3點開會", conn=conn)
    memory.append("7", "action", "已建立『開會』6/25 15:00", conn=conn)
    memory.append("7", "media", "處理檔案 a.png → a-nobg.png", conn=conn)
    memory.append("7", "assistant", "好，已經幫你建立了", conn=conn)
    assert [m["role"] for m in memory.recent("7", conn=conn)] == ["user", "assistant"]


def test_recent_actions_returns_actions_media_in_order(tmp_path):
    # recent_actions()：只回 action/media，依時間升冪，受 k 限制（供常駐「我最近做過的事」）
    conn = _db(tmp_path)
    memory.append("7", "user", "閒聊一句不算動作", conn=conn)
    memory.append("7", "action", "已寄信給 a@b.com", conn=conn)
    memory.append("7", "media", "處理檔案 x.png → x-nobg.png", conn=conn)
    acts = memory.recent_actions("7", conn=conn)
    assert [a["content"] for a in acts] == ["已寄信給 a@b.com", "處理檔案 x.png → x-nobg.png"]
    assert all(a["ts"] for a in acts)
    assert memory.recent_actions("7", k=1, conn=conn) == [acts[-1]]   # k 限制：只取最新 1 筆


def test_short_line_skips_chunk_sync(tmp_path):
    conn = _db(tmp_path)
    mid = memory.append("7", "user", "ok", conn=conn)            # < MEMORY_MIN_CHARS
    row = conn.execute("SELECT chunk_id FROM memories WHERE id=:i", {"i": mid}).fetchone()
    assert row["chunk_id"] is None
    assert conn.execute("SELECT count(*) n FROM chunks").fetchone()["n"] == 0


def test_long_line_syncs_chunk(tmp_path):
    conn = _db(tmp_path)
    mid = memory.append("7", "user", "我下週要去東京出差三天", conn=conn)
    row = conn.execute("SELECT chunk_id FROM memories WHERE id=:i", {"i": mid}).fetchone()
    assert row["chunk_id"] == mid
    ch = conn.execute("SELECT source_type, speaker FROM chunks WHERE id=:i", {"i": mid}).fetchone()
    assert ch["source_type"] == "conversation" and ch["speaker"] == "7"


def test_get_history_is_recent(tmp_path):
    conn = _db(tmp_path)
    memory.append("7", "user", "hi", conn=conn)
    assert memory.get_history("7", conn=conn) == memory.recent("7", conn=conn)


def test_timeline_and_persons(tmp_path):
    conn = _db(tmp_path)
    memory.append("7", "user", "我下週要去東京出差三天", alias="Eric", conn=conn)
    memory.append("7", "assistant", "幫你記下來了", alias="Eric", conn=conn)
    tl = memory.timeline("7", conn=conn)
    assert len(tl) == 2 and tl[0]["ts"] and tl[0]["kind"] in ("user", "assistant")
    ps = memory.persons(conn=conn)
    assert ps and ps[0]["person_id"] == "7" and ps[0]["count"] == 2 and ps[0]["alias"] == "Eric"


def test_clear_removes_memories_and_chunks(tmp_path):
    conn = _db(tmp_path)
    memory.append("7", "user", "我下週要去東京出差三天", conn=conn)   # 會同步 chunk
    memory.clear("7", conn=conn)
    assert conn.execute("SELECT count(*) n FROM memories WHERE person_id='7'").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) n FROM chunks WHERE source_type='conversation'").fetchone()["n"] == 0


def test_clear_all(tmp_path):
    conn = _db(tmp_path)
    memory.append("7", "user", "我下週要去東京出差三天", conn=conn)
    memory.append("8", "action", "寄信給 a@b.com", conn=conn)
    memory.clear_all(conn=conn)
    assert conn.execute("SELECT count(*) n FROM memories").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) n FROM chunks WHERE source_type IN ('conversation','action')").fetchone()["n"] == 0


def test_memory_autocreates_schema_on_fresh_db(tmp_path, monkeypatch):
    """既有 KB 早於 memories 表 → memory 自開連線時要能自建 schema（不靠啟動順序）。"""
    import config
    dbf = str(tmp_path / "fresh.sqlite")          # 全新、未 apply_schema
    monkeypatch.setattr(config, "KB_PATH", dbf)
    memory._schema_ready.discard(dbf)
    mid = memory.append("7", "user", "你好世界這是測試", alias="E")   # conn=None → 自建表 + 同步 chunk
    assert mid
    assert memory.recent("7") == [{"role": "user", "content": "你好世界這是測試"}]


def test_migrate_json(tmp_path, monkeypatch):
    import json as _json
    conn = _db(tmp_path)
    jp = tmp_path / "conversations.json"
    jp.write_text(_json.dumps({"7": [{"role": "user", "content": "舊訊息一"},
                                     {"role": "assistant", "content": "舊回覆一"}]}), encoding="utf-8")
    monkeypatch.setattr(memory, "_JSON_PATH", jp)
    n = memory.migrate_json(conn=conn)
    assert n == 2
    rows = conn.execute("SELECT ts, content FROM memories WHERE person_id='7' ORDER BY rowid").fetchall()
    assert len(rows) == 2 and all(r["ts"] for r in rows)        # 時間戳非空
    assert memory.migrate_json(conn=conn) == 0                  # 再跑不重複
