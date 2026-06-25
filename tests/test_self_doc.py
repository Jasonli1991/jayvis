"""JAYVIS 自我說明自動灌進 KB：隨 repo 出貨、重建索引時 upsert，使用者免手動搬檔。
RAG 問答（answer_context）排除的是 conversation/action，故 source_type='manual' 會被檢索到。"""
import chunks
from db.connection import get_conn, apply_schema
from ingest import self_doc


def _db(tmp_path):
    c = get_conn(str(tmp_path / "kb.sqlite")); apply_schema(c)
    return c


def _stub_embed(monkeypatch):
    # 避免載真 embedding 模型，並計次以驗證 content_hash 短路（內容沒變不重 embed）
    calls = {"n": 0}

    def fake(texts):
        calls["n"] += len(texts)
        return [[0.1] * 8 for _ in texts]

    monkeypatch.setattr(chunks, "embed_texts", fake)
    return calls


def test_sections_splits_by_h2_and_keeps_intro():
    md = "---\ntitle: x\n---\n# 標題\n前言段\n## 第一節\n內容一\n## 第二節\n內容二\n"
    secs = self_doc._sections(md)
    titles = [t for t, _ in secs]
    assert titles[0] == "總覽" and "前言段" in secs[0][1]      # frontmatter 去掉、前言併「總覽」
    assert ("第一節", "內容一") in secs and ("第二節", "內容二") in secs


def test_seed_inserts_manual_chunks_retrievable_by_kb(tmp_path, monkeypatch):
    # 核心保證：self-doc 的 source_type 不在 KB 問答的「真實」排除清單 → 會被 RAG 撈到。
    # 綁 orchestrator 的實際常數（非寫死 tuple）：若有人把 'manual' 加進排除清單，此測試會紅。
    from retrieval.orchestrator import KB_EXCLUDE_SOURCE_TYPES
    _stub_embed(monkeypatch)
    conn = _db(tmp_path)
    n = self_doc.seed(conn)
    assert n > 0
    got = conn.execute(
        "SELECT count(*) c FROM chunks WHERE id LIKE 'selfdoc:%' AND source_type='manual'").fetchone()
    assert got["c"] == n                                      # 確實寫入 manual chunk
    assert self_doc.SOURCE_TYPE == "manual"
    assert self_doc.SOURCE_TYPE not in KB_EXCLUDE_SOURCE_TYPES  # ← 不被 KB 問答排除（真實綁定）


def test_seed_idempotent_and_skips_reembed(tmp_path, monkeypatch):
    calls = _stub_embed(monkeypatch)
    conn = _db(tmp_path)
    n1 = self_doc.seed(conn)
    first = calls["n"]
    assert first > 0
    n2 = self_doc.seed(conn)                                  # 內容沒變：upsert 命中 content_hash、不重 embed
    total = conn.execute("SELECT count(*) c FROM chunks WHERE id LIKE 'selfdoc:%'").fetchone()["c"]
    assert n1 == n2 == total                                  # 不翻倍
    assert calls["n"] == first                                # 第二次 0 次 embed（短路生效）


def test_seed_prunes_removed_sections(tmp_path, monkeypatch):
    # 改版刪段要同步：殘留的舊 selfdoc id 會被清掉
    _stub_embed(monkeypatch)
    conn = _db(tmp_path)
    conn.execute("INSERT INTO chunks (id, source_type, owner, raw_text, content_hash) "
                 "VALUES ('selfdoc:99','manual','owner','殘留舊段','h')")
    self_doc.seed(conn)
    assert conn.execute("SELECT count(*) c FROM chunks WHERE id='selfdoc:99'").fetchone()["c"] == 0


def test_seed_no_doc_returns_zero_and_clears(tmp_path, monkeypatch):
    _stub_embed(monkeypatch)
    monkeypatch.setattr(self_doc, "DOC_PATH", tmp_path / "nope.md")
    conn = _db(tmp_path)
    conn.execute("INSERT INTO chunks (id, source_type, owner, raw_text, content_hash) "
                 "VALUES ('selfdoc:00','manual','owner','x','h')")
    assert self_doc.seed(conn) == 0
    assert conn.execute("SELECT count(*) c FROM chunks WHERE id LIKE 'selfdoc:%'").fetchone()["c"] == 0
