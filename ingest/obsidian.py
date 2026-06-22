import re
from datetime import datetime
from pathlib import Path

import obsidian_folders
from chunks import ChunkRecord, upsert_chunk
from safety import sanitize

MAX_CHARS = 1200
SUB_OVERLAP = 100
DEFAULT_DIRS = ["01_Wiki", "02_Outputs/Projects", "02_Outputs/Q&A",
                "03_Meta/Prompts", "04_Archive/Projects"]

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_links(body: str) -> list:
    """抽 [[wikilink]]，每個取筆記名（去掉 |別名 與 #章節）。回名稱清單（去空）。"""
    out = []
    for raw in _LINK_RE.findall(body):
        name = raw.split("|")[0].split("#")[0].strip()
        if name:
            out.append(name)
    return out


# ── frontmatter（極簡，無 PyYAML 依賴）────────────────────────────────────────
def _parse_yaml_lite(lines: list) -> dict:
    meta, i = {}, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#") or ":" not in line:
            i += 1
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key in ("tags", "aliases"):
            items = []
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
            elif val:
                items = [x.strip().strip("'\"") for x in val.split(",") if x.strip()]
            else:
                j = i + 1
                while j < len(lines) and lines[j].lstrip().startswith("- "):
                    items.append(lines[j].lstrip()[2:].strip().strip("'\""))
                    j += 1
                i = j - 1
            meta[key] = items
        else:
            meta[key] = val.strip("'\"")
        i += 1
    return meta


def parse_frontmatter(text: str):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text
    meta = _parse_yaml_lite(lines[1:end])
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return meta, body


def _parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _note_event_time(meta, fpath):
    """筆記日期：frontmatter updated/created/date 優先，退回檔案 mtime。"""
    for key in ("updated", "created", "date"):
        dt = _parse_date(str(meta.get(key) or ""))
        if dt:
            return dt
    try:
        return datetime.fromtimestamp(fpath.stat().st_mtime)
    except Exception:
        return None


# ── 標題分節（H2+ 為邊界，H1 視為標題）────────────────────────────────────────
def split_sections(body: str):
    """依 H2+ 分節，回 [(heading_path, text)]。H1 視為標題、不進內容、不分節。"""
    sections, stack, cur = [], [], []

    def flush():
        text = "\n".join(cur).strip()
        if text:
            sections.append((" › ".join(t for _, t in stack), text))

    for line in body.splitlines():
        m2 = re.match(r"^(#{2,6})\s+(.*)$", line)
        if m2:
            flush()
            cur.clear()
            level, title = len(m2.group(1)), m2.group(2).strip()
            stack[:] = [(l, t) for (l, t) in stack if l < level]
            stack.append((level, title))
        elif re.match(r"^#\s+.*$", line):
            continue                          # H1：標題行，略過
        else:
            cur.append(line)
    flush()
    return sections


# ── 組塊輔助 ────────────────────────────────────────────────────────────────
def _note_title(meta: dict, body: str, rel: str) -> str:
    if meta.get("title"):
        return str(meta["title"])
    for line in body.splitlines():
        m = re.match(r"^#\s+(.*)$", line)
        if m:
            return m.group(1).strip()
    return Path(rel).stem


def _split_long(text: str, max_chars: int = MAX_CHARS, overlap: int = SUB_OVERLAP):
    if len(text) <= max_chars:
        return [text]
    out, cur = [], ""
    for p in text.split("\n\n"):
        if cur and len(cur) + len(p) + 2 > max_chars:
            out.append(cur.strip())
            cur = (cur[-overlap:] + "\n\n" + p) if overlap else p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur.strip():
        out.append(cur.strip())
    final = []
    for c in out:                              # 單段仍超長 → 硬切
        if len(c) <= max_chars:
            final.append(c)
        else:
            for i in range(0, len(c), max_chars - overlap):
                final.append(c[i:i + max_chars])
    return final


def _breadcrumb(title: str, folder: str, tags: list, heading_path: str, content: str) -> str:
    tagstr = " ".join("#" + t for t in (tags or []))
    head = f"【筆記：{title}｜分類：{folder}" + (f"｜標籤：{tagstr}" if tagstr else "") + "】"
    parts = [head]
    if heading_path:
        parts.append(f"〔章節：{heading_path}〕")
    parts.append(content)
    return "\n".join(parts)


# ── 掃描 / 灌入 ──────────────────────────────────────────────────────────────
def count_md_files(vault_root, include_dirs=DEFAULT_DIRS) -> int:
    """掃描範圍內的 md 檔總數（區分「路徑掃不到東西」與「內容無變化」用）。"""
    vault_root = Path(vault_root)
    n = 0
    for inc in include_dirs:
        target = vault_root / inc
        if target.exists():
            n += sum(1 for _ in target.rglob("*.md"))
    return n


def _scan_files(vault_root, include_dirs):
    vault_root = Path(vault_root)
    for inc in include_dirs:
        target = vault_root / inc
        if not target.exists():
            continue
        for fpath in target.rglob("*.md"):
            yield fpath, str(fpath.relative_to(vault_root))


def _build_name_index(conn, vault_root, include_dirs) -> dict:
    """Pass 1：寫 note_meta（含 is_moc）+ 建 name_index（檔名 stem／title／alias → rel，先到先得）。"""
    name_index = {}
    for fpath, rel in _scan_files(vault_root, include_dirs):
        meta, body = parse_frontmatter(fpath.read_text(encoding="utf-8"))
        title = _note_title(meta, body, rel)
        is_moc = 1 if "moc" in [t.lower() for t in (meta.get("tags") or [])] else 0
        conn.execute("INSERT OR REPLACE INTO note_meta (doc_path, title, is_moc) VALUES (?,?,?)",
                     (rel, title, is_moc))
        for k in [Path(rel).stem, title, *(meta.get("aliases") or [])]:
            kk = (k or "").strip().lower()
            if kk and kk not in name_index:
                name_index[kk] = rel
    return name_index


def ingest_dir(conn, vault_root, include_dirs=DEFAULT_DIRS) -> int:
    name_index = _build_name_index(conn, vault_root, include_dirs)   # Pass 1
    written = 0
    for fpath, rel in _scan_files(vault_root, include_dirs):         # Pass 2
        meta, body = parse_frontmatter(fpath.read_text(encoding="utf-8"))
        ev = _note_event_time(meta, fpath)
        title = _note_title(meta, body, rel)
        tags = meta.get("tags") or []
        folder = obsidian_folders.label_for(rel)
        for sec_idx, (heading_path, sec_text) in enumerate(split_sections(body)):
            for sub_idx, piece in enumerate(_split_long(sec_text)):
                raw = _breadcrumb(title, folder, tags, heading_path, piece)
                s = sanitize(raw)
                if s.blocked:
                    continue
                rec = ChunkRecord(id=f"obsidian::{rel}::{sec_idx}::{sub_idx}",
                                  source_type="obsidian", doc_path=rel, raw_text=s.text,
                                  event_time=ev)
                if upsert_chunk(conn, rec):
                    written += 1
        seen_dst = set()
        for name in extract_links(body):
            dst = name_index.get(name.strip().lower())
            if dst and dst != rel and dst not in seen_dst:
                seen_dst.add(dst)
                conn.execute("INSERT INTO note_links (src, dst) VALUES (?,?)", (rel, dst))
    return written


def ingest_obsidian(conn) -> int:
    from config import OBSIDIAN_PATH
    from db.connection import apply_schema
    apply_schema(conn)                                  # 確保 note_meta/note_links 存在（既有 KB 可能沒有）
    conn.execute("DELETE FROM chunks WHERE source_type='obsidian'")
    conn.execute("DELETE FROM note_links")
    conn.execute("DELETE FROM note_meta")
    return ingest_dir(conn, OBSIDIAN_PATH)
