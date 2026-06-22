from datetime import datetime

from db.connection import get_conn, apply_schema
import ingest.obsidian as ob


def test_parse_date():
    assert ob._parse_date("2026-06-01") == datetime(2026, 6, 1)
    assert ob._parse_date("2026-06-01T10:30") == datetime(2026, 6, 1, 10, 30)
    assert ob._parse_date("亂字串") is None and ob._parse_date("") is None


def test_note_event_time_frontmatter_then_mtime():
    # frontmatter 有日期 → 用它
    assert ob._note_event_time({"updated": "2026-06-10"}, None) == datetime(2026, 6, 10)

    # 無 frontmatter 日期 → 退回檔案 mtime
    class _F:
        def stat(self):
            return type("S", (), {"st_mtime": 1781000000})()   # 任一固定時間

    got = ob._note_event_time({}, _F())
    assert got == datetime.fromtimestamp(1781000000)


def test_ingest_sets_event_time(tmp_path, monkeypatch):
    caps = []
    monkeypatch.setattr(ob, "upsert_chunk", lambda conn, rec: caps.append(rec) or True)
    vault = tmp_path / "vault"
    (vault / "01_Wiki").mkdir(parents=True)
    (vault / "01_Wiki" / "n.md").write_text(
        "---\nupdated: 2026-06-10\n---\n# 標題\n這是一段夠長的內容文字內容文字內容文字。", encoding="utf-8")
    c = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(c)
    ob.ingest_dir(c, str(vault), include_dirs=["01_Wiki"])
    assert caps and all(r.source_type == "obsidian" for r in caps)
    assert caps[0].event_time == datetime(2026, 6, 10)        # chunk 帶上 frontmatter 日期
