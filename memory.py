"""搭檔記憶：DB-backed 時間軸日誌（取代舊 JSON）。對談/動作/媒體連同時間戳寫入 memories，
有意義者同步進 chunks（語意回想用）。每人隔離；owner 全看。"""
import json
import uuid
from datetime import datetime
from pathlib import Path

import config
from chunks import ChunkRecord, upsert_chunk
from db.connection import apply_schema, get_conn

_MEMORY_SOURCE_TYPES = ("conversation", "action")
_JSON_PATH = Path.home() / ".n" / "conversations.json"
_schema_ready = set()       # 已套過 schema 的 DB 路徑（避免每次重套）


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _with_conn(conn):
    """傳入 conn（測試自管 schema）直接用；否則自開 KB 連線並確保 schema 已建
    （既有 KB 可能早於 memories 表 → 自建，不靠啟動順序）。"""
    if conn is not None:
        return conn, False
    c = get_conn()
    if config.KB_PATH not in _schema_ready:
        apply_schema(c)
        _schema_ready.add(config.KB_PATH)
    return c, True


def append(person_id, kind, content, alias=None, meta=None, ts=None, conn=None, consolidate=True):
    content = (content or "").strip()
    if not content:
        return None
    c, own = _with_conn(conn)
    try:
        mid = uuid.uuid4().hex
        ts = ts or _now()
        chunk_id = None
        if kind in ("action", "media") or len(content) >= config.MEMORY_MIN_CHARS:
            chunk_id = mid
            st = "action" if kind in ("action", "media") else "conversation"
            upsert_chunk(c, ChunkRecord(id=chunk_id, source_type=st, raw_text=content,
                                        owner=config.OWNER_KEY, speaker=str(person_id), author=alias,
                                        event_time=datetime.now()))
        c.execute(
            "INSERT INTO memories (id, ts, person_id, person_alias, kind, content, meta, chunk_id) "
            "VALUES (:id,:ts,:pid,:alias,:kind,:content,:meta,:cid)",
            {"id": mid, "ts": ts, "pid": str(person_id), "alias": alias, "kind": kind,
             "content": content, "meta": json.dumps(meta, ensure_ascii=False) if meta else None,
             "cid": chunk_id})
        if kind in ("user", "assistant") and consolidate:   # 批次匯入時關掉逐則整併、最後整併一次（見 import_turns）
            try:
                import memory_consolidate
                memory_consolidate.maybe_consolidate(person_id)
            except Exception:
                pass                               # 整併失敗不可影響 append
        return mid
    finally:
        if own:
            c.close()


# ── owner 聊天記憶 匯入／匯出（限定 JAYVIS JSON 格式，可來回） ──
MEMORY_FORMAT_VERSION = 1


def export_person(person_id, conn=None):
    """匯出某人的聊天記憶（user/assistant 對話），依時間升冪回 [{ts, role, content}]。"""
    c, own = _with_conn(conn)
    try:
        rows = c.execute(
            "SELECT ts, kind, content FROM memories WHERE person_id=:p AND kind IN ('user','assistant') "
            "ORDER BY rowid", {"p": str(person_id)}).fetchall()
        return [{"ts": r["ts"], "role": r["kind"], "content": r["content"]} for r in rows]
    finally:
        if own:
            c.close()


def build_export(person_id, conn=None) -> dict:
    """包成 JAYVIS 記憶檔格式（匯出產生、匯入只收這個）。"""
    return {"jayvis_memory_version": MEMORY_FORMAT_VERSION, "exported_at": _now(),
            "person": "owner", "turns": export_person(person_id, conn=conn)}


def validate_import(data) -> tuple:
    """嚴格驗證是否為 JAYVIS 記憶格式。回 (clean_turns, error)；error 非 None＝格式不符（限定格式）。"""
    if not isinstance(data, dict):
        return None, "不是有效的 JAYVIS 記憶檔（應為 JSON 物件）"
    if data.get("jayvis_memory_version") != MEMORY_FORMAT_VERSION:
        return None, f"缺 jayvis_memory_version 或版本不符（需 {MEMORY_FORMAT_VERSION}）"
    turns = data.get("turns")
    if not isinstance(turns, list):
        return None, "缺 turns 陣列"
    clean = []
    for t in turns:
        if not isinstance(t, dict):
            continue
        role, content = t.get("role"), t.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            clean.append({"role": role, "content": content, "ts": t.get("ts")})
    if not clean:
        return None, "turns 內沒有有效對話（role 需 user/assistant、content 為非空字串）"
    return clean, None


def import_turns(person_id, turns, alias=None, clear_first=False, progress=None, conn=None) -> int:
    """把外部聊天記憶逐則灌進 person 的記憶，走完整管線（embedding）；最後整併一次。回匯入筆數。
    turns 須已通過 validate_import。progress(done, total) 選填，供面板顯示進度。"""
    c, own = _with_conn(conn)
    n = 0
    try:
        if clear_first:
            clear(str(person_id), conn=c)
        total = len(turns)
        for i, t in enumerate(turns):
            mid = append(str(person_id), t["role"], t["content"], alias=alias, ts=t.get("ts"),
                         meta={"imported": True}, conn=c, consolidate=False)  # 批次：不逐則整併
            if mid:
                n += 1
            if progress and (i % 20 == 0 or i == total - 1):
                progress(i + 1, total)
        if n:                                       # 最後整併一次（建立長期認識）
            try:
                import memory_consolidate
                memory_consolidate.maybe_consolidate(str(person_id))
            except Exception:
                pass
        return n
    finally:
        if own:
            c.close()


def recent(person_id, k=None, conn=None):
    k = k or config.MEMORY_RECENT_TURNS
    c, own = _with_conn(conn)
    try:
        rows = c.execute(
            "SELECT kind, content FROM memories WHERE person_id=:p AND kind IN ('user','assistant') "
            "ORDER BY rowid DESC LIMIT :lim", {"p": str(person_id), "lim": k * 2}).fetchall()
        return [{"role": r["kind"], "content": r["content"]} for r in reversed(rows)]
    finally:
        if own:
            c.close()


def get_history(person_id, conn=None):
    return recent(person_id, conn=conn)


def recent_actions(person_id, k=None, conn=None):
    """撈某人最近 k 筆動作/媒體（依時間升冪），供 owner 私訊常駐「我最近做過的事」區塊。
    這些 kind 被 recent()（對話歷史）排除，否則 JAYVIS 下一輪看不到自己剛做了什麼 →
    體感「換了個人」。回 [{ts, content}]。"""
    k = k or config.MEMORY_RECENT_ACTIONS
    c, own = _with_conn(conn)
    try:
        rows = c.execute(
            "SELECT ts, content FROM memories WHERE person_id=:p AND kind IN ('action','media') "
            "ORDER BY rowid DESC LIMIT :lim", {"p": str(person_id), "lim": k}).fetchall()
        return [{"ts": r["ts"], "content": r["content"]} for r in reversed(rows)]
    finally:
        if own:
            c.close()


def recall(person_id, query, n=None, owner=False, conn=None):
    """依 person scope 做語意 + FTS 回想；回帶時間戳的文字（''＝無）。owner=True 不過濾人。"""
    from retrieval.hybrid import hybrid_search
    n = n or config.MEMORY_RECALL_N
    c, own = _with_conn(conn)
    try:
        speaker = None if owner else str(person_id)
        cands = hybrid_search(c, query, owner=config.OWNER_KEY, out_k=n,
                              source_types=_MEMORY_SOURCE_TYPES, speaker=speaker)
        if not cands:
            return ""
        lines = []
        for cand in cands:
            row = c.execute("SELECT ts FROM memories WHERE chunk_id=:cid", {"cid": cand.id}).fetchone()
            ts = row["ts"] if row else ""
            lines.append(f"[{ts}] {cand.raw_text}")
        return "\n".join(lines)
    finally:
        if own:
            c.close()


def timeline(person_id, n=50, conn=None):
    c, own = _with_conn(conn)
    try:
        rows = c.execute(
            "SELECT ts, kind, content FROM memories WHERE person_id=:p ORDER BY rowid DESC LIMIT :n",
            {"p": str(person_id), "n": n}).fetchall()
        return [{"ts": r["ts"], "kind": r["kind"], "content": r["content"]} for r in rows]
    finally:
        if own:
            c.close()


def conversations_between(start, end, exclude_person_id=None, conn=None):
    """請假彙整用：撈 ts 區間 [start, end] 的對話（可排除某 person_id），依 ts 升冪。"""
    c, own = _with_conn(conn)
    try:
        rows = c.execute(
            "SELECT ts, person_alias, person_id, kind, content FROM memories "
            "WHERE ts >= :s AND ts <= :e AND (:excl IS NULL OR person_id != :excl) "
            "ORDER BY ts",
            {"s": start, "e": end, "excl": exclude_person_id}).fetchall()
        return [{"ts": r["ts"], "person_alias": r["person_alias"], "person_id": r["person_id"],
                 "kind": r["kind"], "content": r["content"]} for r in rows]
    finally:
        if own:
            c.close()


def persons(conn=None):
    c, own = _with_conn(conn)
    try:
        rows = c.execute(
            "SELECT person_id, max(person_alias) alias, max(ts) last_ts, count(*) count "
            "FROM memories GROUP BY person_id ORDER BY last_ts DESC").fetchall()
        return [{"person_id": r["person_id"], "alias": r["alias"],
                 "last_ts": r["last_ts"], "count": r["count"]} for r in rows]
    finally:
        if own:
            c.close()


def backfill_alias(person_id, alias, conn=None):
    """補上某人尚缺的別名（person_alias 為空者）。供名字解析後存回。"""
    if not alias:
        return
    c, own = _with_conn(conn)
    try:
        c.execute("UPDATE memories SET person_alias=:a "
                  "WHERE person_id=:p AND (person_alias IS NULL OR person_alias='')",
                  {"a": alias, "p": str(person_id)})
    finally:
        if own:
            c.close()


def clear(person_id, conn=None):
    c, own = _with_conn(conn)
    try:
        c.execute("DELETE FROM chunks WHERE id IN "
                  "(SELECT chunk_id FROM memories WHERE person_id=:p AND chunk_id IS NOT NULL)",
                  {"p": str(person_id)})
        c.execute("DELETE FROM memories WHERE person_id=:p", {"p": str(person_id)})
    finally:
        if own:
            c.close()


def clear_all(conn=None):
    c, own = _with_conn(conn)
    try:
        c.execute("DELETE FROM chunks WHERE source_type IN ('conversation','action')")
        c.execute("DELETE FROM memories")
    finally:
        if own:
            c.close()


def migrate_json(conn=None):
    """一次性把舊 conversations.json 匯入 memories（無時間 → 用檔案 mtime 近似）。回匯入筆數。"""
    if not _JSON_PATH.exists():
        return 0
    try:
        data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    ts = datetime.fromtimestamp(_JSON_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    c, own = _with_conn(conn)
    n = 0
    try:
        for pid, msgs in (data or {}).items():
            exists = c.execute("SELECT 1 FROM memories WHERE person_id=:p LIMIT 1", {"p": str(pid)}).fetchone()
            if exists:
                continue                       # 該人已有 → 不重複匯入
            for m in msgs:
                role = m.get("role")
                if role not in ("user", "assistant"):
                    continue
                append(str(pid), role, m.get("content", ""), ts=ts,
                       meta={"migrated": True}, conn=c)
                n += 1
        return n
    finally:
        if own:
            c.close()
