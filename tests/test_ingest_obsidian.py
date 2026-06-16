from pathlib import Path
from ingest.obsidian import ingest_dir, count_md_files


def test_count_md_files(tmp_path):
    (tmp_path / "01_Wiki").mkdir()
    (tmp_path / "01_Wiki" / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "01_Wiki" / "b.md").write_text("y", encoding="utf-8")
    assert count_md_files(tmp_path, ["01_Wiki"]) == 2
    assert count_md_files(tmp_path / "no_such_dir", ["01_Wiki"]) == 0


def test_ingest_writes_chunks_with_provenance(conn, tmp_path):
    d = tmp_path / "01_Wiki"
    d.mkdir()
    (d / "note.md").write_text("pgvector 是 Postgres 的向量擴充。" * 30, encoding="utf-8")
    n = ingest_dir(conn, tmp_path, ["01_Wiki"])
    assert n >= 1
    row = conn.execute("SELECT source_type, doc_path FROM chunks LIMIT 1").fetchone()
    assert row["source_type"] == "obsidian"
    assert "note.md" in row["doc_path"]


def test_ingest_skips_secret_files(conn, tmp_path):
    d = tmp_path / "01_Wiki"; d.mkdir()
    (d / "leak.md").write_text("token: sk-ant-AAAA1111BBBB2222CCCC3333DDDD4444", encoding="utf-8")
    ingest_dir(conn, tmp_path, ["01_Wiki"])
    n = conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]
    assert n == 0  # secret-containing chunk blocked
