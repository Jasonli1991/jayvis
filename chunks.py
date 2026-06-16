import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from embeddings import embed_texts


@dataclass
class ChunkRecord:
    id: str
    source_type: str
    raw_text: str
    owner: str = "owner"
    repo: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    pr_number: int | None = None
    channel: str | None = None
    thread_id: str | None = None
    speaker: str | None = None
    permalink: str | None = None
    doc_path: str | None = None
    export_version: str | None = None
    author: str | None = None
    event_time: datetime | None = None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def citation_of(rec) -> str:
    st = getattr(rec, "source_type", None) or rec.get("source_type")
    g = (lambda k: getattr(rec, k, None) if not isinstance(rec, dict) else rec.get(k))
    if st == "git":
        return f"commit {(g('commit_sha') or '')[:8]} @ {g('repo')}"
    if st == "chat":
        return f"{g('channel') or g('speaker')} 對話"
    if st == "obsidian":
        return f"筆記 {g('doc_path')}"
    return st or "unknown"


def upsert_chunk(conn, rec: ChunkRecord) -> bool:
    h = content_hash(rec.raw_text)
    existing = conn.execute(
        "SELECT content_hash FROM chunks WHERE id=:id", {"id": rec.id}
    ).fetchone()
    if existing and existing["content_hash"] == h:
        return False
    emb = embed_texts([rec.raw_text])[0]
    params = {
        **rec.__dict__,
        "content_hash": h,
        "embedding": np.asarray(emb, dtype=np.float32).tobytes(),
        "event_time": rec.event_time.isoformat() if rec.event_time else None,
    }
    conn.execute(
        """
        INSERT INTO chunks (id, source_type, owner, repo, file_path, commit_sha,
            pr_number, channel, thread_id, speaker, permalink, doc_path,
            export_version, author, event_time, raw_text, content_hash, embedding)
        VALUES (:id,:source_type,:owner,:repo,:file_path,:commit_sha,
            :pr_number,:channel,:thread_id,:speaker,:permalink,:doc_path,
            :export_version,:author,:event_time,:raw_text,:content_hash,:embedding)
        ON CONFLICT (id) DO UPDATE SET
            raw_text=excluded.raw_text, content_hash=excluded.content_hash,
            embedding=excluded.embedding, ingested_at=datetime('now'),
            event_time=excluded.event_time
        """,
        params,
    )
    return True
