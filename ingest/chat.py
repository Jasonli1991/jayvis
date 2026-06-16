from chunks import ChunkRecord, upsert_chunk
from safety import sanitize

MESSAGES_PER_CHUNK = 40


def write_chat_chunk(conn, channel: str, idx: int, lines: list[str]) -> ChunkRecord:
    raw = f"【{channel}】近期對話紀錄\n\n" + "\n".join(lines)
    s = sanitize(raw)
    rec = ChunkRecord(
        id=f"chat::{channel}::{idx}", source_type="chat",
        channel=channel, raw_text=s.text if not s.blocked else "")
    if not s.blocked:
        upsert_chunk(conn, rec)
    return rec
