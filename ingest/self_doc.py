"""把 JAYVIS 自我說明（docs/JAYVIS-使用說明.md）灌進 KB，讓每個部署「開箱即懂自己」——
隨 repo 一起出貨、重建索引時自動 upsert，使用者不必手動把檔案搬進 vault 再重建。
來源在 repo（不在使用者 vault），所以走 RAG 檢索（問到才取用、平時不占對話 context）。"""
import re
from datetime import datetime
from pathlib import Path

import config
from chunks import ChunkRecord, upsert_chunk
from db.connection import get_conn

DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "JAYVIS-使用說明.md"
SOURCE_TYPE = "manual"
_ID_PREFIX = "selfdoc:"


def is_seeded(conn=None) -> bool:
    """KB 裡是否已有自我說明（manual chunks）。供面板顯示狀態、bot 判斷是否引導 owner 去灌。
    便宜查詢（LIMIT 1）；conn 為 None 時自開 KB 連線。"""
    own = conn is None
    c = conn or get_conn()
    try:
        return c.execute("SELECT 1 FROM chunks WHERE source_type=:t LIMIT 1",
                         {"t": SOURCE_TYPE}).fetchone() is not None
    except Exception:
        return False
    finally:
        if own:
            c.close()


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def _sections(text: str):
    """以 H2（## ）切段，回 [(標題, 內容)]。H2 之前的前言（# 標題＋引言）併成「總覽」段。
    每段獨立成 chunk → 問到哪段就只取那段，避免整份灌進 context。"""
    text = _strip_frontmatter(text)
    parts = re.split(r"(?m)^##[ \t]+", text)
    out = []
    intro = parts[0].strip()
    if intro:
        out.append(("總覽", intro))
    for seg in parts[1:]:
        head, _, body = seg.partition("\n")
        title, body = head.strip(), body.strip()
        if title and body:
            out.append((title, body))
    return out


def seed(conn) -> int:
    """重建 selfdoc:* chunks。先 upsert 目前各段（內容沒變者 upsert_chunk 會命中 content_hash、
    不重新 embed），再刪掉本輪沒寫到的殘留舊段（改版/刪段同步）——避免一開頭就 DELETE 把
    hash 短路打掉、每次全量 re-embed。回寫入段數；說明檔不存在回 0。"""
    if not DOC_PATH.exists():
        conn.execute("DELETE FROM chunks WHERE id LIKE :p", {"p": _ID_PREFIX + "%"})
        return 0
    ids = []
    for i, (title, body) in enumerate(_sections(DOC_PATH.read_text(encoding="utf-8"))):
        cid = f"{_ID_PREFIX}{i:02d}"
        upsert_chunk(conn, ChunkRecord(id=cid, source_type=SOURCE_TYPE,
                                       raw_text=f"【JAYVIS 使用說明｜{title}】\n{body}",
                                       owner=config.OWNER_KEY, doc_path=f"JAYVIS 使用說明 § {title}",
                                       event_time=datetime.now()))
        ids.append(cid)
    placeholders = ",".join(f":id{i}" for i in range(len(ids)))
    conn.execute(f"DELETE FROM chunks WHERE id LIKE :p AND id NOT IN ({placeholders})",
                 {"p": _ID_PREFIX + "%", **{f"id{i}": v for i, v in enumerate(ids)}})
    return len(ids)
