"""owner 聊天記憶 匯入／匯出：格式嚴格驗證、import→export 來回、先清空、端點守門。"""
import sqlite3

import chunks
import config
import memory
import memory_consolidate
from db.connection import apply_schema


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_schema(c)
    return c


def _no_embed_no_consolidate(monkeypatch):
    monkeypatch.setattr(chunks, "embed_texts", lambda ts: [[0.1] * 1024 for _ in ts])   # 不載真模型
    monkeypatch.setattr(memory_consolidate, "maybe_consolidate", lambda pid: None)


def test_validate_import_rejects_bad_formats():
    assert memory.validate_import([])[1]                                    # 非 dict
    assert memory.validate_import({})[1]                                    # 缺 version
    assert memory.validate_import({"jayvis_memory_version": 1})[1]          # 缺 turns
    assert memory.validate_import({"jayvis_memory_version": 1, "turns": []})[1]   # 無有效對話
    assert memory.validate_import({"jayvis_memory_version": 99,
                                   "turns": [{"role": "user", "content": "x"}]})[1]  # 版本不符
    turns, err = memory.validate_import({"jayvis_memory_version": 1, "turns": [
        {"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"},
        {"role": "system", "content": "略過"}, {"role": "user", "content": "   "}]})
    assert err is None and [t["role"] for t in turns] == ["user", "assistant"]   # 過濾非 user/assistant 與空白


def test_import_then_export_roundtrip(monkeypatch):
    _no_embed_no_consolidate(monkeypatch)
    c = _conn()
    turns = [{"role": "user", "content": "我是 Jason，做產品經理"},
             {"role": "assistant", "content": "了解，Jason，記住了"}]
    assert memory.import_turns("123", turns, conn=c) == 2
    out = memory.export_person("123", conn=c)
    assert [(t["role"], t["content"]) for t in out] == \
        [("user", "我是 Jason，做產品經理"), ("assistant", "了解，Jason，記住了")]


def test_import_clear_first(monkeypatch):
    _no_embed_no_consolidate(monkeypatch)
    c = _conn()
    memory.append("123", "user", "舊的記憶內容應被清掉", conn=c, consolidate=False)
    memory.import_turns("123", [{"role": "user", "content": "全新匯入的內容"}], clear_first=True, conn=c)
    assert [t["content"] for t in memory.export_person("123", conn=c)] == ["全新匯入的內容"]


def test_build_export_format(monkeypatch):
    _no_embed_no_consolidate(monkeypatch)
    c = _conn()
    memory.append("123", "user", "哈囉這是一段測試內容", conn=c, consolidate=False)
    data = memory.build_export("123", conn=c)
    assert data["jayvis_memory_version"] == 1 and data["person"] == "owner"
    assert data["turns"][0]["role"] == "user"


def test_rebuild_from_memory_iterates_windows(monkeypatch):
    """匯入後重建長期認識：分窗逐步用模型合併、最後寫回、回報進度。"""
    import user_profile
    turns = [{"ts": "t", "role": "user", "content": f"訊息{i}"} for i in range(40)]
    monkeypatch.setattr(user_profile.memory, "export_person", lambda pid: turns)
    monkeypatch.setattr(user_profile, "get", lambda pid: "")
    written = {}
    monkeypatch.setattr(user_profile, "_write", lambda pid, prof: written.update(prof=prof))
    calls = []

    def fake_gen(model, system, messages, max_output_tokens=600):
        calls.append(1)
        return "畫像v" + str(len(calls))

    monkeypatch.setattr(user_profile, "generate", fake_gen)
    monkeypatch.setattr(user_profile, "_update_portrait", lambda pid, prof: None)   # 本測只看分窗，不牽動頭像抽取
    prog = []
    user_profile.rebuild_from_memory("123", window=16, progress=lambda d, t: prog.append((d, t)))
    assert len(calls) == 3                  # 40 輪 / 窗 16 → 3 窗 → 3 次模型呼叫
    assert written.get("prof") == "畫像v3"  # 逐窗合併、最後結果寫回
    assert prog[-1] == (40, 40)             # 進度到底


def test_rebuild_caps_max_turns(monkeypatch):
    """有界：超過 max_turns 只取最近的，避免大批匯入打爆模型呼叫。"""
    import user_profile
    turns = [{"ts": "t", "role": "user", "content": f"m{i}"} for i in range(100)]
    monkeypatch.setattr(user_profile.memory, "export_person", lambda pid: turns)
    monkeypatch.setattr(user_profile, "get", lambda pid: "")
    monkeypatch.setattr(user_profile, "_write", lambda pid, prof: None)
    seen = []
    monkeypatch.setattr(user_profile, "generate",
                        lambda model, system, messages, max_output_tokens=600: seen.append(messages[0]["content"]) or "x")
    monkeypatch.setattr(user_profile, "_update_portrait", lambda pid, prof: None)   # 本測只看分窗
    user_profile.rebuild_from_memory("123", max_turns=20, window=10)
    assert len(seen) == 2                   # 上限 20 輪 / 窗 10 → 2 窗
    assert "m99" in seen[-1]                # 取的是最近的（含最後一筆 m99）


def test_rebuild_extracts_portrait_at_end(monkeypatch):
    """重建完，會用最終畫像抽一次後台塗鴉頭像的臉部特徵。"""
    import user_profile
    turns = [{"ts": "t", "role": "user", "content": f"訊息{i}"} for i in range(20)]
    monkeypatch.setattr(user_profile.memory, "export_person", lambda pid: turns)
    monkeypatch.setattr(user_profile, "get", lambda pid: "")
    monkeypatch.setattr(user_profile, "_write", lambda pid, prof: None)
    monkeypatch.setattr(user_profile, "generate",
                        lambda model, system, messages, max_output_tokens=600: "最終畫像")
    got = {}
    monkeypatch.setattr(user_profile, "_update_portrait", lambda pid, prof: got.update(pid=pid, prof=prof))
    user_profile.rebuild_from_memory("123", window=16)
    assert got.get("prof") == "最終畫像"     # 以最終畫像抽頭像特徵


def test_export_endpoint_blocks_when_owner_unset(monkeypatch):
    from panel import app as app_mod
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 0)
    r = app_mod.app.test_client().post("/api/memory/export", json={},
                                       headers={"Origin": "http://127.0.0.1:8765"})
    assert r.get_json()["ok"] is False                                      # 沒設 owner → 擋下


def test_import_endpoint_rejects_bad_format(monkeypatch, tmp_path):
    from panel import app as app_mod
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 123)
    bad = tmp_path / "bad.json"
    bad.write_text('{"foo": 1}', encoding="utf-8")                          # 非 JAYVIS 記憶格式
    r = app_mod.app.test_client().post("/api/memory/import", json={"path": str(bad)},
                                       headers={"Origin": "http://127.0.0.1:8765"})
    j = r.get_json()
    assert j["ok"] is False and "格式" in j["error"]
