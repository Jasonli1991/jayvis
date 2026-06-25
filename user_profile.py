"""owner 學習畫像（仿 Hermes USER.md）：批次抽取耐久事實、合併、注入。owner-only。"""
import logging
import threading

import config
import memory
from db.connection import get_conn, apply_schema
from llm import generate

_log = logging.getLogger("jayvis")

PROFILE_EVERY_N = 6
PROFILE_MAX_CHARS = 1500
PROFILE_RECENT_TURNS = 12
REBUILD_MAX_TURNS = 400      # 匯入後重建：最多取最近這麼多輪（有界，避免大批匯入打爆模型呼叫）
REBUILD_WINDOW = 16          # 每窗送模型的輪數（逐窗合併進畫像）

_schema_ready = set()
_running = set()         # 正在背景抽取畫像的 person（避免短時間重複抽取）；in-memory，僅作並發鎖


def reset():             # 測試/手動重置用
    _schema_ready.clear()
    _running.clear()


def _conn():
    c = get_conn()
    if config.KB_PATH not in _schema_ready:
        apply_schema(c)
        _schema_ready.add(config.KB_PATH)
    return c


def get(person_id) -> str:
    c = _conn()
    try:
        row = c.execute("SELECT profile FROM person_profiles WHERE person_id=:p",
                        {"p": str(person_id)}).fetchone()
        return row["profile"] if row else ""
    finally:
        c.close()


def _write(person_id, profile):
    c = _conn()
    try:
        c.execute(
            "INSERT INTO person_profiles (person_id, profile, updated_at) "
            "VALUES (:p, :pr, datetime('now','localtime')) "
            "ON CONFLICT(person_id) DO UPDATE SET profile=excluded.profile, updated_at=excluded.updated_at",
            {"p": str(person_id), "pr": profile})
    finally:
        c.close()


def clear(person_id):
    c = _conn()
    try:
        c.execute("DELETE FROM person_profiles WHERE person_id=:p", {"p": str(person_id)})
    finally:
        c.close()


def prompt_block(person_id) -> str:
    prof = get(person_id).strip()
    if not prof:
        return ""
    return (f"## 你對 {config.OWNER_NAME} 的長期認識（觀察累積、非權威，可能有誤；"
            f"與上面的設定衝突時以設定為準）\n{prof}")


def _profile_updated_at(person_id):
    c = _conn()
    try:
        row = c.execute("SELECT updated_at FROM person_profiles WHERE person_id=:p",
                        {"p": str(person_id)}).fetchone()
        return row["updated_at"] if row else None
    finally:
        c.close()


def _turns_since(person_id, since_ts) -> int:
    """某人在 since_ts 之後（None＝全部）的對話則數（user/assistant）。
    持久化來源（memories 表）→ bot 重啟也不歸零；動作/媒體互動也記在這、一併算進去。"""
    c = _conn()
    try:
        if since_ts:
            row = c.execute(
                "SELECT count(*) n FROM memories WHERE person_id=:p "
                "AND kind IN ('user','assistant') AND ts > :t",
                {"p": str(person_id), "t": since_ts}).fetchone()
        else:
            row = c.execute(
                "SELECT count(*) n FROM memories WHERE person_id=:p "
                "AND kind IN ('user','assistant')", {"p": str(person_id)}).fetchone()
        return row["n"] if row else 0
    finally:
        c.close()


def _fmt_turns(turns) -> str:
    out = []
    for t in turns:
        who = config.OWNER_NAME if t.get("role") == "user" else "搭檔"
        out.append(f"{who}：{t.get('content', '')}")
    return "\n".join(out)


def _extract_merge(current, turns) -> str:
    """用模型從一批對話抽取耐久資訊、與現有畫像合併。失敗或空 → 回原畫像（不遺失）。"""
    sys = ("從以下對話抽取關於使用者的『耐久』資訊（偏好、工作風格、長期專案/角色、慣用做法）。"
           "忽略一次性瑣事、時事、寒暄。把新資訊與『現有畫像』合併成精簡條列、去重、"
           f"矛盾以新的為準、總長不超過 {PROFILE_MAX_CHARS} 字。只輸出更新後的畫像，不要多餘文字。")
    user = f"現有畫像：\n{current or '（空）'}\n\n最近對話：\n{_fmt_turns(turns)}"
    try:
        out = generate(model=config.MODEL_GENERAL, system=sys,
                       messages=[{"role": "user", "content": user}], max_output_tokens=600)
    except Exception:
        _log.info("👤 畫像抽取失敗 → 保留舊畫像")
        return current
    prof = (out or "").strip()[:PROFILE_MAX_CHARS]
    return prof or current


def update_now(person_id):
    """抽取近 N 輪的耐久資訊、與現有畫像合併、寫回 DB。任何失敗 → 不動。"""
    turns = memory.recent(person_id, k=PROFILE_RECENT_TURNS)
    if not turns:
        return
    prof = _extract_merge(get(person_id), turns)
    if prof and prof != get(person_id):
        _write(person_id, prof)


def rebuild_from_memory(person_id, max_turns=REBUILD_MAX_TURNS, window=REBUILD_WINDOW, progress=None) -> str:
    """從某人完整對話史「重建」長期認識：分窗逐步抽取＋合併、寫回 DB。用於聊天記憶匯入後，
    讓搭檔一開始就認識使用者。有界（最多最近 max_turns 輪）、可回報進度。回最終畫像。"""
    turns = memory.export_person(person_id)          # [{ts, role, content}] 升冪
    if not turns:
        return ""
    turns = turns[-max_turns:]                       # 有界：只取最近 max_turns 輪
    current = get(person_id)
    total = len(turns)
    for i in range(0, total, window):
        current = _extract_merge(current, turns[i:i + window])    # 逐窗合併（turns 帶 role/content，_fmt_turns 可用）
        if progress:
            progress(min(i + window, total), total)
    if current:
        _write(person_id, current)
    return current


def _spawn(person_id):
    pid = str(person_id)
    if pid in _running:                  # 已有背景抽取在跑 → 不重複（避免一連串訊息狂觸發）
        return
    _running.add(pid)

    def _run():
        try:
            update_now(pid)
        finally:
            _running.discard(pid)
    threading.Thread(target=_run, daemon=True).start()


def maybe_update(person_id):
    """不用記憶體計數器（重啟會歸零、且動作回合不算）：改看「上次更新畫像後又累積了幾則對話」。
    來源是持久化的 memories.ts vs person_profiles.updated_at → bot 重啟也不歸零。
    沒畫像時計全部對話、有畫像時只計 updated_at 之後的新對話；達門檻就背景抽取一次。"""
    if _turns_since(person_id, _profile_updated_at(person_id)) >= PROFILE_EVERY_N * 2:
        _spawn(person_id)
