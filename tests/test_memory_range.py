import uuid
from db.connection import get_conn, apply_schema
import memory


def _db(tmp_path):
    c = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(c)
    return c


def _ins(c, ts, pid, alias, content):
    c.execute("INSERT INTO memories (id, ts, person_id, person_alias, kind, content) VALUES (?,?,?,?,?,?)",
              (uuid.uuid4().hex, ts, str(pid), alias, "user", content))


def test_conversations_between_range_and_exclude(tmp_path):
    c = _db(tmp_path)
    _ins(c, "2026-06-19 10:00:00", 111, "Alice", "假期前")        # 區間前
    _ins(c, "2026-06-20 09:00:00", 111, "Alice", "問A")
    _ins(c, "2026-06-21 14:00:00", 222, "Bob", "問B")
    _ins(c, "2026-06-25 23:30:00", 222, "Bob", "問C")            # 區間內含尾日
    _ins(c, "2026-06-26 09:00:00", 111, "Alice", "假期後")        # 區間後
    _ins(c, "2026-06-21 10:00:00", 6803, "Jason", "owner自己")    # owner，要排除
    rows = memory.conversations_between("2026-06-20", "2026-06-25 23:59:59",
                                        exclude_person_id="6803", conn=c)
    assert [r["content"] for r in rows] == ["問A", "問B", "問C"]   # 區間內、排除 owner、依 ts 升冪


def test_conversations_between_no_exclude(tmp_path):
    c = _db(tmp_path)
    _ins(c, "2026-06-20 09:00:00", 6803, "Jason", "x")
    rows = memory.conversations_between("2026-06-20", "2026-06-21", conn=c)
    assert len(rows) == 1 and rows[0]["content"] == "x"          # 不排除
