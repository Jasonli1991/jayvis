"""Obsidian 資料夾語意：ingest 麵包屑分類 + assistant prompt legend 共用。"""
import json
from pathlib import Path

_PATH = Path(__file__).parent / "prompts" / "obsidian_folders.json"
_DEFAULT = {
    "01_Wiki": {"label": "知識條目", "note": "原子化知識，通常較可靠"},
    "02_Outputs/Projects": {"label": "專案產出", "note": "專案文件與決策紀錄"},
    "02_Outputs/Q&A": {"label": "問答紀錄", "note": "歷史問答，反映當時情境，未必是現況"},
    "03_Meta/Prompts": {"label": "Prompt 模板", "note": "提示詞範本，不是事實陳述"},
    "04_Archive": {"label": "封存", "note": "已歸檔，可能過時"},
}


def load() -> dict:
    try:
        if _PATH.exists():
            return json.loads(_PATH.read_text(encoding="utf-8")) or _DEFAULT
    except Exception:
        pass
    return _DEFAULT


def label_for(rel: str) -> str:
    rel = (rel or "").replace("\\", "/")
    best, best_len = "筆記", -1
    for prefix, info in load().items():
        p = prefix.replace("\\", "/")
        if (rel == p or rel.startswith(p + "/")) and len(p) > best_len:
            best, best_len = info.get("label", "筆記"), len(p)
    return best


def prompt_legend() -> str:
    lines = ["## 知識庫資料夾語意（解讀來源時參考）"]
    seen = set()
    for info in load().values():
        lab = info.get("label", "")
        if lab and lab not in seen:
            seen.add(lab)
            lines.append(f"- {lab}：{info.get('note', '')}")
    return "\n".join(lines)
