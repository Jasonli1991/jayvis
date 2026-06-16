"""Obsidian 雙鏈/MOC 圖譜：沿命中筆記的 1-hop 鄰居（含 backlinks、MOC 優先）擴展 context。"""
from pathlib import Path


def neighbors(conn, doc_paths: list, max_notes: int = 3) -> list:
    """命中筆記的出鏈 + 入鏈鄰居，排除自己、MOC 優先、取前 max_notes。"""
    if not doc_paths:
        return []
    ph = ",".join("?" * len(doc_paths))
    rows = conn.execute(
        f"SELECT dst AS nb FROM note_links WHERE src IN ({ph}) "
        f"UNION SELECT src AS nb FROM note_links WHERE dst IN ({ph})",
        list(doc_paths) + list(doc_paths)).fetchall()
    selfset = set(doc_paths)
    cand, seen = [], set()
    for r in rows:
        nb = r["nb"]
        if nb in selfset or nb in seen:
            continue
        seen.add(nb)
        cand.append(nb)
    if not cand:
        return []
    ph2 = ",".join("?" * len(cand))
    moc = {r["doc_path"]: r["is_moc"] for r in
           conn.execute(f"SELECT doc_path, is_moc FROM note_meta WHERE doc_path IN ({ph2})", cand).fetchall()}
    cand.sort(key=lambda d: (0 if moc.get(d) else 1, d))     # MOC 先、其次字典序（穩定可測）
    return cand[:max_notes]


def expand_context(conn, doc_paths: list, max_notes: int = 3, excerpt_chars: int = 500) -> str:
    """鄰居筆記的標題＋首塊節錄組成一段 context；任何失敗或無鄰居 → 回 ''。"""
    try:
        nbs = neighbors(conn, doc_paths, max_notes=max_notes)
        if not nbs:
            return ""
        lines = ["## 相關筆記（沿你的雙鏈擴展）"]
        for d in nbs:
            m = conn.execute("SELECT title FROM note_meta WHERE doc_path=?", (d,)).fetchone()
            title = (m["title"] if m and m["title"] else Path(d).stem)
            row = conn.execute(
                "SELECT raw_text FROM chunks WHERE doc_path=? AND source_type='obsidian' ORDER BY id LIMIT 1",
                (d,)).fetchone()
            excerpt = (row["raw_text"][:excerpt_chars] if row and row["raw_text"] else "")
            lines.append(f"- [[{title}]]（{d}）\n  {excerpt}")
        return "\n".join(lines)
    except Exception:
        return ""
