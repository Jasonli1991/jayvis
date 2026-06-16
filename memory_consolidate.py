"""記憶整併：摘要式、有界、背景自動。失敗安全——摘要失敗或寫入失敗都不遺失原始。"""
import logging
import threading
import uuid
from datetime import datetime

import config
from chunks import ChunkRecord, upsert_chunk
from db.connection import get_conn, apply_schema
from llm import generate

_log = logging.getLogger("jayvis")

KEEP_RECENT = 40         # 每人保留最近幾筆對談原始
THRESHOLD = 120          # 對談筆數超過就觸發
MIN_BATCH = 20           # 要整的最舊批至少這麼多才值得

_running = set()         # per-person 鎖（記憶體）

_QUOTA_HINT = ("429", "resource_exhausted", "quota", "exceeded")


def _err_reason(e) -> str:
    s = str(e).lower()
    if any(k in s for k in _QUOTA_HINT):
        return "模型額度可能用完（429/quota）"
    return f"{e.__class__.__name__}: {str(e)[:80]}"


def reset():             # 測試用
    _running.clear()


def _conv_count(conn, person_id) -> int:
    return conn.execute(
        "SELECT count(*) c FROM memories WHERE person_id=:p "
        "AND kind IN ('user','assistant','summary')", {"p": str(person_id)}).fetchone()["c"]


def _summarize(text) -> str:
    sys = ("把以下同一個人的舊對談摘要成精簡幾點，保留長期重要事實／決定／偏好，丟瑣事；"
           "繁體中文、只輸出摘要，不要多餘文字。")
    try:
        out = generate(model=config.MODEL_GENERAL, system=sys,
                       messages=[{"role": "user", "content": (text or "")[:6000]}],
                       max_output_tokens=400)
        return (out or "").strip()
    except Exception as e:
        _log.warning("🧹 記憶摘要失敗：%s → 跳過整併、原始記憶不動", _err_reason(e))
        return ""


def consolidate(person_id):
    pid = str(person_id)
    if pid in _running:
        return
    _running.add(pid)
    c = get_conn()
    apply_schema(c)
    try:
        rows = c.execute(
            "SELECT id, chunk_id, kind, content FROM memories "
            "WHERE person_id=:p AND kind IN ('user','assistant','summary') "
            "ORDER BY rowid ASC", {"p": pid}).fetchall()
        old = rows[:-KEEP_RECENT] if len(rows) > KEEP_RECENT else []
        if len(old) < MIN_BATCH:
            return                                              # 不夠多 → 不動
        text = "\n".join(f"{r['kind']}：{r['content']}" for r in old)
        summary = _summarize(text)                             # 動 DB 之前；失敗/空 → 不刪任何東西
        if not summary:
            _log.info("🧹 整併跳過 %s：摘要失敗或為空 → 原始記憶不動（下次累積再試）", pid)
            return
        old_ids = [r["id"] for r in old]
        old_chunks = [r["chunk_id"] for r in old if r["chunk_id"]]
        c.execute("BEGIN IMMEDIATE")
        try:
            sid = uuid.uuid4().hex
            upsert_chunk(c, ChunkRecord(id=sid, source_type="conversation", raw_text=summary,
                                        owner=config.OWNER_KEY, speaker=pid, author=None, event_time=datetime.now()))
            c.execute("INSERT INTO memories (id, ts, person_id, person_alias, kind, content, meta, chunk_id) "
                      "VALUES (:id, datetime('now','localtime'), :p, NULL, 'summary', :ct, NULL, :cid)",
                      {"id": uuid.uuid4().hex, "p": pid, "ct": summary, "cid": sid})
            qm = ",".join("?" * len(old_ids))
            c.execute(f"DELETE FROM memories WHERE id IN ({qm})", old_ids)
            if old_chunks:
                qm2 = ",".join("?" * len(old_chunks))
                c.execute(f"DELETE FROM chunks WHERE id IN ({qm2})", old_chunks)
            c.execute("COMMIT")
            _log.info("🧹 整併 %s：%d 筆 → 1 條摘要", pid, len(old))
        except Exception:
            c.execute("ROLLBACK")                              # 半套 → 全退，原始完整留著
            _log.exception("🧹 整併交易失敗 %s → 已 ROLLBACK，原始記憶完整保留", pid)
    except Exception:
        _log.exception("🧹 整併失敗 %s → 未變更任何記憶", pid)
    finally:
        c.close()
        _running.discard(pid)


def _spawn(person_id):
    threading.Thread(target=consolidate, args=(str(person_id),), daemon=True).start()


def maybe_consolidate(person_id):
    pid = str(person_id)
    if pid in _running:
        return
    c = get_conn()
    apply_schema(c)
    try:
        over = _conv_count(c, pid) > THRESHOLD
    finally:
        c.close()
    if over:
        _spawn(pid)
