from db.connection import get_conn, apply_schema

import memory_consolidate as mc


def _db(tmp_path):
    # 用 conftest 隔離的 config.KB_PATH —— consolidate 內部 get_conn() 開的就是這個 DB
    c = get_conn()
    apply_schema(c)
    return c


def _seed(conn, person, n, kind="user", base=0, chunked=True):
    """插 n 筆某 kind 的記憶（chunked=True 同時插 conversation/action chunk）。"""
    for i in range(n):
        mid = f"{person}-{kind}-{base + i}"
        cid = mid if chunked else None
        if chunked:
            conn.execute("INSERT INTO chunks (id, source_type, owner, raw_text, content_hash, speaker) "
                         "VALUES (?,?,?,?,?,?)",
                         (cid, "action" if kind in ("action", "media") else "conversation",
                          "owner", f"訊息{base + i}", f"h{kind}{base + i}", person))
        conn.execute("INSERT INTO memories (id, person_id, kind, content, chunk_id) VALUES (?,?,?,?,?)",
                     (mid, person, kind, f"訊息{base + i}", cid))


def test_conv_count_excludes_actions(tmp_path):
    c = _db(tmp_path)
    _seed(c, "7", 4, "user")
    _seed(c, "7", 2, "assistant", base=100)
    _seed(c, "7", 1, "summary", base=200)
    _seed(c, "7", 3, "action", base=300)        # 動作不算
    assert mc._conv_count(c, "7") == 7           # 4 + 2 + 1


def test_summarize_calls_llm(monkeypatch):
    monkeypatch.setattr(mc, "generate", lambda **k: "摘要結果")
    assert mc._summarize("一些舊對談") == "摘要結果"


def test_summarize_error_returns_blank(monkeypatch):
    def boom(**k):
        raise RuntimeError("quota")
    monkeypatch.setattr(mc, "generate", boom)
    assert mc._summarize("x") == ""


def _fake_upsert(conn, rec):
    conn.execute("INSERT INTO chunks (id, source_type, owner, raw_text, content_hash, speaker) "
                 "VALUES (?,?,?,?,?,?)", (rec.id, rec.source_type, rec.owner, rec.raw_text, "hs", rec.speaker))
    return True


def _counts(tmp_path, person):
    v = _db(tmp_path)
    try:
        kinds = [r["kind"] for r in v.execute(
            "SELECT kind FROM memories WHERE person_id=:p ORDER BY rowid", {"p": person}).fetchall()]
        nchunks = v.execute("SELECT count(*) c FROM chunks WHERE speaker=:p", {"p": person}).fetchone()["c"]
        return kinds, nchunks
    finally:
        v.close()


def test_consolidate_summarizes_old_keeps_recent(tmp_path, monkeypatch):
    mc.reset()
    monkeypatch.setattr(mc, "KEEP_RECENT", 5)
    monkeypatch.setattr(mc, "MIN_BATCH", 2)
    monkeypatch.setattr(mc, "_summarize", lambda text: "摘要：舊對談重點")
    monkeypatch.setattr(mc, "upsert_chunk", _fake_upsert)
    c = _db(tmp_path); _seed(c, "7", 12, "user"); c.close()   # 12 筆對談
    mc.consolidate("7")
    kinds, nchunks = _counts(tmp_path, "7")
    assert kinds.count("summary") == 1                         # 1 條摘要
    assert kinds.count("user") == 5                            # 最近 5 筆原始保留
    assert nchunks == 6                                        # 5 最近 + 1 摘要（舊 7 chunk 已刪）


def test_consolidate_keeps_actions(tmp_path, monkeypatch):
    mc.reset()
    monkeypatch.setattr(mc, "KEEP_RECENT", 2)
    monkeypatch.setattr(mc, "MIN_BATCH", 2)
    monkeypatch.setattr(mc, "_summarize", lambda text: "摘")
    monkeypatch.setattr(mc, "upsert_chunk", _fake_upsert)
    c = _db(tmp_path); _seed(c, "7", 6, "user"); _seed(c, "7", 3, "action", base=50); c.close()
    mc.consolidate("7")
    kinds, _ = _counts(tmp_path, "7")
    assert kinds.count("action") == 3                          # 動作記錄不被碰


def test_consolidate_summarize_fail_no_change(tmp_path, monkeypatch):
    mc.reset()
    monkeypatch.setattr(mc, "KEEP_RECENT", 5)
    monkeypatch.setattr(mc, "MIN_BATCH", 2)
    monkeypatch.setattr(mc, "_summarize", lambda text: "")     # 摘要失敗
    monkeypatch.setattr(mc, "upsert_chunk", _fake_upsert)
    c = _db(tmp_path); _seed(c, "7", 12, "user"); c.close()
    mc.consolidate("7")
    kinds, nchunks = _counts(tmp_path, "7")
    assert kinds.count("user") == 12 and "summary" not in kinds and nchunks == 12   # 完全不動


def test_consolidate_rollback_on_write_fail(tmp_path, monkeypatch):
    mc.reset()
    monkeypatch.setattr(mc, "KEEP_RECENT", 5)
    monkeypatch.setattr(mc, "MIN_BATCH", 2)
    monkeypatch.setattr(mc, "_summarize", lambda text: "摘要")

    def boom(conn, rec):
        raise RuntimeError("embed fail")
    monkeypatch.setattr(mc, "upsert_chunk", boom)             # 寫摘要 chunk 失敗
    c = _db(tmp_path); _seed(c, "7", 12, "user"); c.close()
    mc.consolidate("7")
    kinds, nchunks = _counts(tmp_path, "7")
    assert kinds.count("user") == 12 and "summary" not in kinds and nchunks == 12   # ROLLBACK，原始完整


def test_consolidate_min_batch_no_op(tmp_path, monkeypatch):
    mc.reset()
    monkeypatch.setattr(mc, "KEEP_RECENT", 5)
    monkeypatch.setattr(mc, "MIN_BATCH", 10)
    monkeypatch.setattr(mc, "_summarize", lambda text: "摘")
    monkeypatch.setattr(mc, "upsert_chunk", _fake_upsert)
    c = _db(tmp_path); _seed(c, "7", 12, "user"); c.close()   # old = 7 < MIN_BATCH 10
    mc.consolidate("7")
    kinds, _ = _counts(tmp_path, "7")
    assert kinds.count("user") == 12 and "summary" not in kinds


def test_maybe_consolidate_gate(tmp_path, monkeypatch):
    mc.reset()
    monkeypatch.setattr(mc, "THRESHOLD", 5)
    spawned = []
    monkeypatch.setattr(mc, "_spawn", lambda pid: spawned.append(pid))
    c = _db(tmp_path); _seed(c, "7", 5, "user"); c.close()
    mc.maybe_consolidate("7")
    assert spawned == []                                       # 5 不 > 5
    c = _db(tmp_path); _seed(c, "7", 1, "user", base=99); c.close()
    mc.maybe_consolidate("7")
    assert spawned == ["7"]                                    # 6 > 5 → 觸發


def test_maybe_consolidate_skips_when_locked(tmp_path, monkeypatch):
    mc.reset()
    monkeypatch.setattr(mc, "THRESHOLD", 5)
    spawned = []
    monkeypatch.setattr(mc, "_spawn", lambda pid: spawned.append(pid))
    mc._running.add("7")                                       # 整併中
    c = _db(tmp_path); _seed(c, "7", 10, "user"); c.close()
    mc.maybe_consolidate("7")
    assert spawned == []                                       # 鎖中 → 不重複觸發


import logging


def test_summarize_logs_reason_on_error(monkeypatch, caplog):
    def boom(**k):
        raise RuntimeError("quota exceeded 429")
    monkeypatch.setattr(mc, "generate", boom)
    with caplog.at_level(logging.WARNING, logger="jayvis"):
        assert mc._summarize("x") == ""
    assert "摘要失敗" in caplog.text                  # 有記原因提示
    assert "額度" in caplog.text or "quota" in caplog.text.lower()


def test_consolidate_logs_skip_on_empty_summary(tmp_path, monkeypatch, caplog):
    mc.reset()
    monkeypatch.setattr(mc, "KEEP_RECENT", 5)
    monkeypatch.setattr(mc, "MIN_BATCH", 2)
    monkeypatch.setattr(mc, "_summarize", lambda text: "")     # 摘要空/失敗
    c = _db(tmp_path); _seed(c, "7", 12, "user"); c.close()
    with caplog.at_level(logging.INFO, logger="jayvis"):
        mc.consolidate("7")
    assert "跳過" in caplog.text and "摘要" in caplog.text       # 後續處置：跳過、不動


def test_consolidate_logs_rollback_with_handling(tmp_path, monkeypatch, caplog):
    mc.reset()
    monkeypatch.setattr(mc, "KEEP_RECENT", 5)
    monkeypatch.setattr(mc, "MIN_BATCH", 2)
    monkeypatch.setattr(mc, "_summarize", lambda text: "摘要")

    def boom(conn, rec):
        raise RuntimeError("embed fail")
    monkeypatch.setattr(mc, "upsert_chunk", boom)
    c = _db(tmp_path); _seed(c, "7", 12, "user"); c.close()
    with caplog.at_level(logging.INFO, logger="jayvis"):
        mc.consolidate("7")
    assert "ROLLBACK" in caplog.text and "保留" in caplog.text   # 原因(traceback)+ 後續處置


import memory


def test_append_triggers_on_conversation(monkeypatch):
    called = []
    monkeypatch.setattr(mc, "maybe_consolidate", lambda pid: called.append(("c", pid)))
    memory.append("7", "user", "這是一句夠長的對談內容用來觸發")
    assert called == [("c", "7")]


def test_append_not_trigger_on_action(monkeypatch):
    called = []
    monkeypatch.setattr(mc, "maybe_consolidate", lambda pid: called.append(("c", pid)))
    memory.append("7", "action", "做了某個動作")
    assert called == []                                        # 動作不觸發整併
