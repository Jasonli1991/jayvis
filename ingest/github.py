from datetime import datetime, timezone
from chunks import ChunkRecord, upsert_chunk
from safety import sanitize


def commit_to_chunk(conn, repo: str, sha: str, author: str, date: str, msg: str) -> ChunkRecord:
    raw = f"[{repo}] {date} {author}: {msg}"
    s = sanitize(raw)
    ev = None
    try:
        ev = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    except Exception:
        ev = None
    rec = ChunkRecord(
        id=f"git::{repo}::{sha}", source_type="git",
        repo=repo, commit_sha=sha, author=author, event_time=ev,
        raw_text=s.text if not s.blocked else "")
    if not s.blocked:
        upsert_chunk(conn, rec)
    return rec
