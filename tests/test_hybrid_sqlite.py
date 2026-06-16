import numpy as np

import retrieval.hybrid as H
from db.connection import get_conn, apply_schema


def _unit(v):
    a = np.asarray(v, np.float32)
    return (a / np.linalg.norm(a)).astype(np.float32)


def _seed(conn, rows):
    for cid, text, vec in rows:
        conn.execute(
            "INSERT INTO chunks(id, source_type, owner, raw_text, content_hash, embedding) "
            "VALUES (:id,'obsidian','owner',:t,:h,:e)",
            {"id": cid, "t": text, "h": cid, "e": _unit(vec).tobytes()},
        )


def test_dense_knn_picks_nearest(tmp_path, monkeypatch):
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    _seed(conn, [
        ("a", "綠界金流串接審核中", [1, 0, 0]),
        ("b", "錢包功能與用戶頁面", [0, 1, 0]),
        ("c", "今天天氣很好出門",   [0, 0, 1]),
    ])
    monkeypatch.setattr(H, "embed_query", lambda q: _unit([0.95, 0.1, 0.0]))
    cands = H.hybrid_search(conn, "完全無關鍵字命中xyz", owner="owner", out_k=3)
    assert cands[0].id == "a"          # dense 最近者排第一
    conn.close()


def test_sparse_fts_contributes(tmp_path, monkeypatch):
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    _seed(conn, [
        ("a", "綠界金流串接審核中", [0, 0, 1]),
        ("b", "錢包功能與用戶頁面", [0, 1, 0]),
        ("c", "今天天氣很好出門",   [1, 0, 0]),
    ])
    # 查詢向量貼近 c，但關鍵字「金流串接」只命中 a → a 應入選
    monkeypatch.setattr(H, "embed_query", lambda q: _unit([0.9, 0.1, 0.1]))
    cands = H.hybrid_search(conn, "金流串接", owner="owner", out_k=3)
    ids = {c.id for c in cands}
    assert "a" in ids
    conn.close()


def test_owner_filter(tmp_path, monkeypatch):
    conn = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(conn)
    conn.execute("INSERT INTO chunks(id,source_type,owner,raw_text,content_hash,embedding) "
                 "VALUES ('z','obsidian','someone_else','綠界金流串接',' z',:e)",
                 {"e": _unit([1, 0, 0]).tobytes()})
    monkeypatch.setattr(H, "embed_query", lambda q: _unit([1, 0, 0]))
    cands = H.hybrid_search(conn, "金流串接", owner="owner", out_k=3)
    assert cands == []                 # 別的 owner 不回
    conn.close()
