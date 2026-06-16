from ingest import obsidian as ob


def test_extract_links_variants():
    body = "看 [[A]] 和 [[B|別名]]，還有 [[C#章節]]；一行兩個 [[D]] [[E]]。"
    assert ob.extract_links(body) == ["A", "B", "C", "D", "E"]


def test_extract_links_none():
    assert ob.extract_links("沒有任何連結的內文") == []


def test_parse_frontmatter_inline_list():
    meta, body = ob.parse_frontmatter("---\ntitle: 我的筆記\ntags: [ai, rag]\n---\n內文第一行")
    assert meta["title"] == "我的筆記"
    assert meta["tags"] == ["ai", "rag"]
    assert body == "內文第一行"


def test_parse_frontmatter_block_list():
    meta, body = ob.parse_frontmatter("---\ntags:\n  - a\n  - b\n---\nx")
    assert meta["tags"] == ["a", "b"] and body == "x"


def test_parse_frontmatter_none():
    meta, body = ob.parse_frontmatter("沒有 frontmatter 的內文")
    assert meta == {} and body == "沒有 frontmatter 的內文"


def test_parse_frontmatter_unterminated_is_safe():
    meta, body = ob.parse_frontmatter("---\ntitle: x\n沒有結尾")
    assert meta == {} and body == "---\ntitle: x\n沒有結尾"


def test_split_sections_by_h2_h3():
    body = "# 標題\n前言段\n## 設計\n設計內文\n### 資料流\n流程內文"
    secs = ob.split_sections(body)
    paths = [p for p, _ in secs]
    assert "" in paths                       # H1 後到第一個 ## 的前言（path 空）
    assert "設計" in paths
    assert "設計 › 資料流" in paths
    intro = dict(secs)[""]
    assert "前言段" in intro and "# 標題" not in intro   # H1 不進內容


def test_split_sections_no_heading():
    secs = ob.split_sections("純內文沒有標題")
    assert secs == [("", "純內文沒有標題")]


from db.connection import get_conn, apply_schema


def _db(tmp_path):
    c = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(c); return c


def test_ingest_dir_builds_breadcrumb(tmp_path):
    vault = tmp_path / "vault"
    (vault / "02_Outputs" / "Q&A").mkdir(parents=True)
    (vault / "02_Outputs" / "Q&A" / "note.md").write_text(
        "---\ntitle: 匯率問答\ntags: [finance, fx]\n---\n# 匯率問答\n前言\n## 結論\n美元走弱",
        encoding="utf-8")
    conn = _db(tmp_path)
    n = ob.ingest_dir(conn, vault, include_dirs=["02_Outputs/Q&A"])
    assert n >= 2
    rows = [r["raw_text"] for r in conn.execute("SELECT raw_text FROM chunks").fetchall()]
    joined = "\n".join(rows)
    assert "筆記：匯率問答" in joined
    assert "分類：問答紀錄" in joined          # 來自 obsidian_folders.label_for
    assert "#finance" in joined and "#fx" in joined
    assert "章節：結論" in joined and "美元走弱" in joined


def test_ingest_dir_subsplits_long_section(tmp_path):
    vault = tmp_path / "vault"
    (vault / "01_Wiki").mkdir(parents=True)
    big = "\n\n".join([f"段落{i} " + "字" * 300 for i in range(6)])   # 遠超 1200
    (vault / "01_Wiki" / "big.md").write_text(f"# 大筆記\n## 主節\n{big}", encoding="utf-8")
    conn = _db(tmp_path)
    ob.ingest_dir(conn, vault, include_dirs=["01_Wiki"])
    n = conn.execute("SELECT count(*) c FROM chunks WHERE source_type='obsidian'").fetchone()["c"]
    assert n >= 2                              # 過長節 → 多塊


import config


def test_ingest_obsidian_wipes_old(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    conn.execute("INSERT INTO chunks (id, source_type, owner, raw_text, content_hash) "
                 "VALUES ('obsidian::old::0','obsidian','owner','舊切法殘留','h')")
    vault = tmp_path / "vault"
    (vault / "01_Wiki").mkdir(parents=True)
    (vault / "01_Wiki" / "a.md").write_text("# 新筆記\n新內容夠長一點點", encoding="utf-8")
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(vault))   # ingest_obsidian 內 from config import OBSIDIAN_PATH 取當前值
    ob.ingest_obsidian(conn)
    ids = [r["id"] for r in conn.execute("SELECT id FROM chunks WHERE source_type='obsidian'").fetchall()]
    assert "obsidian::old::0" not in ids                        # 舊的被清掉
    assert any(i.startswith("obsidian::01_Wiki/a.md") for i in ids)   # 新的有灌


def test_ingest_builds_note_meta_links_and_moc(tmp_path):
    vault = tmp_path / "vault"
    (vault / "01_Wiki").mkdir(parents=True)
    (vault / "01_Wiki" / "A.md").write_text(
        "---\ntitle: A\n---\n# A\n連到 [[B]] 和 [[不存在]]", encoding="utf-8")
    (vault / "01_Wiki" / "B.md").write_text(
        "---\ntitle: B\ntags: [moc]\n---\n# B\n回連 [[A]]", encoding="utf-8")
    conn = _db(tmp_path)
    ob.ingest_dir(conn, vault, include_dirs=["01_Wiki"])
    # note_meta：B 是 moc、A 不是
    assert conn.execute("SELECT is_moc FROM note_meta WHERE doc_path='01_Wiki/B.md'").fetchone()["is_moc"] == 1
    assert conn.execute("SELECT is_moc FROM note_meta WHERE doc_path='01_Wiki/A.md'").fetchone()["is_moc"] == 0
    # note_links：A→B、B→A；解不到的 [[不存在]] 不寫
    edges = {(r["src"], r["dst"]) for r in conn.execute("SELECT src, dst FROM note_links").fetchall()}
    assert ("01_Wiki/A.md", "01_Wiki/B.md") in edges
    assert ("01_Wiki/B.md", "01_Wiki/A.md") in edges
    assert all("不存在" not in dst for _, dst in edges)


def test_ingest_obsidian_wipes_links_and_meta(tmp_path, monkeypatch):
    conn = _db(tmp_path)
    conn.execute("INSERT INTO note_meta (doc_path, title, is_moc) VALUES ('old.md','old',0)")
    conn.execute("INSERT INTO note_links (src, dst) VALUES ('old.md','x.md')")
    conn.execute("INSERT INTO chunks (id, source_type, owner, raw_text, content_hash) "
                 "VALUES ('obsidian::old::0','obsidian','owner','舊殘留','h')")
    vault = tmp_path / "vault"
    (vault / "01_Wiki").mkdir(parents=True)
    (vault / "01_Wiki" / "a.md").write_text("# 新筆記\n新內容夠長一點點", encoding="utf-8")
    monkeypatch.setattr(config, "OBSIDIAN_PATH", str(vault))
    ob.ingest_obsidian(conn)
    assert conn.execute("SELECT count(*) c FROM note_meta WHERE doc_path='old.md'").fetchone()["c"] == 0
    assert conn.execute("SELECT count(*) c FROM note_links WHERE src='old.md'").fetchone()["c"] == 0
    assert conn.execute("SELECT count(*) c FROM note_meta WHERE doc_path='01_Wiki/a.md'").fetchone()["c"] == 1
