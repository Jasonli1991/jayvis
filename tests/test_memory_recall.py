import memory
from db.connection import get_conn, apply_schema


def _db(tmp_path):
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    return conn


def test_recall_is_person_scoped(tmp_path):
    conn = _db(tmp_path)
    memory.append("100", "user", "我下週要去東京出差三天", conn=conn)
    memory.append("200", "user", "我下週要去東京出差三天", conn=conn)
    out = memory.recall("100", "東京出差", conn=conn)
    assert "東京" in out                      # 有回想到自己的
    assert out.count("東京") == 1             # 不撈別人的（人別隔離）


def test_recall_owner_sees_all(tmp_path):
    conn = _db(tmp_path)
    memory.append("100", "user", "同事說要去東京出差三天", conn=conn)
    memory.append("999", "action", "建立行事曆：6/15 與 Max 開會", conn=conn)
    out = memory.recall("999", "東京 開會", owner=True, conn=conn)
    assert "東京" in out and "開會" in out      # owner 全看


def test_recall_has_timestamp(tmp_path):
    conn = _db(tmp_path)
    memory.append("100", "user", "我下週要去東京出差三天", conn=conn)
    out = memory.recall("100", "東京", conn=conn)
    assert "[" in out and "]" in out           # 帶 [時間] 前綴


def test_recall_empty_when_none(tmp_path):
    conn = _db(tmp_path)
    assert memory.recall("100", "任何東西", conn=conn) == ""
