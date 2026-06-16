import numpy as np

from retrieval.hybrid import hybrid_search


def _insert(conn, id, text, vec):
    conn.execute(
        "INSERT INTO chunks (id, source_type, owner, raw_text, content_hash, embedding) "
        "VALUES (?,'obsidian','owner',?,?,?)",
        (id, text, id, np.asarray(vec, np.float32).tobytes()),
    )


def test_sparse_leg_catches_exact_identifier(conn):
    _insert(conn, "a", "錯誤訊息 NullPointerException at LoginService", [0.0] * 1024)
    _insert(conn, "b", "今天天氣很好跟程式無關", [0.0] * 1024)
    res = hybrid_search(conn, "NullPointerException", out_k=5)
    assert res[0].id == "a"


def test_dense_leg_ranks_by_vector(conn):
    v_close = [1.0] + [0.0] * 1023
    v_far = [0.0, 1.0] + [0.0] * 1022
    _insert(conn, "near", "向量相近的內容", v_close)
    _insert(conn, "far", "向量很遠的內容", v_far)
    from retrieval.hybrid import hybrid_search_vec
    res = hybrid_search_vec(conn, query_text="zzz", qvec=v_close, out_k=5)
    assert res[0].id == "near"
