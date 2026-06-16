from dataclasses import dataclass

import numpy as np

from embeddings import embed_query

_META_COLS = ("repo", "file_path", "commit_sha", "pr_number", "channel",
              "thread_id", "speaker", "permalink", "doc_path", "author")


@dataclass
class Candidate:
    id: str
    raw_text: str
    source_type: str
    rrf_score: float
    meta: dict


def _row_to_candidate(row, score: float) -> Candidate:
    return Candidate(
        id=row["id"], raw_text=row["raw_text"], source_type=row["source_type"],
        rrf_score=float(score),
        meta={c: row[c] for c in _META_COLS},
    )


def _filter_sql(prefix, source_types, exclude_source_types, speaker, params):
    """回傳要 AND 進 WHERE 的片段清單；prefix 是欄位前綴（'' 或 'c.'）。"""
    frags = []
    if source_types:
        keys = [f"st{i}" for i in range(len(source_types))]
        frags.append(f"{prefix}source_type IN ({','.join(':' + k for k in keys)})")
        params.update({k: s for k, s in zip(keys, source_types)})
    if exclude_source_types:
        keys = [f"xst{i}" for i in range(len(exclude_source_types))]
        frags.append(f"{prefix}source_type NOT IN ({','.join(':' + k for k in keys)})")
        params.update({k: s for k, s in zip(keys, exclude_source_types)})
    if speaker is not None:
        frags.append(f"{prefix}speaker = :sp")
        params["sp"] = speaker
    return frags


def _dense_ranks(conn, qvec, owner, k, source_types=None, exclude_source_types=None, speaker=None) -> dict:
    params = {"o": owner}
    where = ["owner=:o", "embedding IS NOT NULL"]
    where += _filter_sql("", source_types, exclude_source_types, speaker, params)
    rows = conn.execute(f"SELECT rowid, embedding FROM chunks WHERE {' AND '.join(where)}", params).fetchall()
    if not rows:
        return {}
    M = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    ids = [r["rowid"] for r in rows]
    sims = M @ np.asarray(qvec, dtype=np.float32)
    order = np.argsort(-sims)[:k]
    return {ids[i]: rank for rank, i in enumerate(order, start=1)}


def _sparse_ranks(conn, query, owner, k, source_types=None, exclude_source_types=None, speaker=None) -> dict:
    fts = '"' + query.replace('"', '""') + '"'
    params = {"q": fts, "o": owner, "k": k}
    where = ["chunks_fts MATCH :q", "c.owner = :o"]
    where += _filter_sql("c.", source_types, exclude_source_types, speaker, params)
    try:
        rows = conn.execute(
            "SELECT chunks_fts.rowid AS rowid FROM chunks_fts "
            "JOIN chunks c ON c.rowid = chunks_fts.rowid "
            f"WHERE {' AND '.join(where)} ORDER BY bm25(chunks_fts) LIMIT :k", params).fetchall()
    except Exception:
        return {}      # 查詢過短（<3 字無 trigram）或語法問題 → 略過 sparse
    return {r["rowid"]: rank for rank, r in enumerate(rows, start=1)}


def hybrid_search_vec(conn, query_text, qvec, owner="owner", k=20, out_k=20, rrf_k=60,
                      source_types=None, exclude_source_types=None, speaker=None):
    dense = _dense_ranks(conn, qvec, owner, k, source_types, exclude_source_types, speaker)
    sparse = _sparse_ranks(conn, query_text, owner, k, source_types, exclude_source_types, speaker)
    scores: dict = {}
    for rid, rank in dense.items():
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (rrf_k + rank)
    for rid, rank in sparse.items():
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (rrf_k + rank)
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:out_k]
    out = []
    for rid, score in top:
        row = conn.execute("SELECT * FROM chunks WHERE rowid = :r", {"r": rid}).fetchone()
        if row:
            out.append(_row_to_candidate(row, score))
    return out


def hybrid_search(conn, query, owner="owner", k=20, out_k=20, rrf_k=60,
                  source_types=None, exclude_source_types=None, speaker=None):
    return hybrid_search_vec(conn, query, embed_query(query), owner, k, out_k, rrf_k,
                             source_types, exclude_source_types, speaker)
