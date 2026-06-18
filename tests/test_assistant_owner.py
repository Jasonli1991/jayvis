import assistant


def test_build_owner_system_framing():
    s = assistant.build_owner_system("", "")
    assert "本人" in s                         # 本人框架
    assert "一般知識" in s                       # 可用一般知識答（不再硬性來源免責）
    assert "不要編造" in s                       # 不編造個人事實
    assert "代表他回答同事" not in s             # 不含對外代言


def test_build_owner_system_includes_rag_and_status():
    s = assistant.build_owner_system("某知識片段XYZ", "專案狀態ABC")
    assert "某知識片段XYZ" in s and "專案狀態ABC" in s


import config


def _result(abstain, context="", source_types=None):
    return type("R", (), {"abstain": abstain, "context": context,
                          "citations": [], "source_types": source_types or []})()


def _patch_common(monkeypatch, seen):
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)
    monkeypatch.setattr(assistant.user_profile, "prompt_block", lambda pid: "")
    monkeypatch.setattr(assistant.user_profile, "maybe_update", lambda pid: None)
    monkeypatch.setattr(assistant, "generate",
                        lambda **kw: seen.update(system=kw["system"]) or "本人回覆")


def test_owner_dm_does_not_abstain(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))   # 撈不到
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    out = assistant.compose_reply(6803, "我在想一個架構問題")
    assert out == "本人回覆"                       # 沒回 ABSTAIN
    assert "本人" in seen["system"]                # 走 owner prompt


def test_colleague_dm_best_effort_no_kb(monkeypatch):
    # 同事私訊、KB 撈不到 → 不再回固定 ABSTAIN，改盡力答並掛無 KB 守則
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    out = assistant.compose_reply(999, "不存在的問題")          # 非 owner
    assert out == "本人回覆"                                     # generate 有跑（盡力答）
    assert out != assistant.ABSTAIN_REPLY
    assert "絕不編造他的事" in seen["system"]                   # 掛無 KB 守則


def test_owner_in_group_no_memory_recall(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    recall_calls = {"n": 0}
    monkeypatch.setattr(assistant.memory, "recall",
                        lambda *a, **k: recall_calls.__setitem__("n", recall_calls["n"] + 1) or "私人記憶XYZ")
    seen = {}
    _patch_common(monkeypatch, seen)
    out = assistant.compose_reply(6803, "大家覺得呢", group_context="群組脈絡")
    assert out == "本人回覆"
    assert "不需對外代言" in seen["system"]        # owner prompt（非同事 persona 巧合）
    assert "代表他回答同事" not in seen["system"]  # 不是對外 persona
    assert "群組脈絡" in seen["system"]            # 有群組上下文
    assert recall_calls["n"] == 0                  # 群組不 recall → 私人記憶不外洩
    assert "私人記憶XYZ" not in seen["system"]


def test_owner_search_injects(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    monkeypatch.setattr(assistant.websearch, "formulate_query", lambda *a, **k: "q")
    monkeypatch.setattr(assistant.websearch, "search",
                        lambda q, n=5: [{"title": "台股收紅", "url": "http://x", "content": "加權指數上漲"}])
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))   # KB 無
    seen = {}
    _patch_common(monkeypatch, seen)
    out = assistant.compose_reply(6803, "今天台股怎樣")
    assert out == "本人回覆"
    assert "加權指數上漲" in seen["system"] and "http://x" in seen["system"]


def test_owner_search_failed_discloses(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    monkeypatch.setattr(assistant.websearch, "formulate_query", lambda *a, **k: "q")
    monkeypatch.setattr(assistant.websearch, "search", lambda q, n=5: None)   # 失敗（額度/連線）
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    seen = {}
    _patch_common(monkeypatch, seen)
    out = assistant.compose_reply(6803, "今天股價")
    assert "本人回覆" in out                       # bot 仍用自己知識答了
    assert out.startswith("⚠️") and "搜尋" in out   # 開頭明確告知搜尋失敗
    assert "加權指數" not in seen["system"]         # 沒有注入（因為失敗）


def test_owner_search_empty_no_disclosure(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    monkeypatch.setattr(assistant.websearch, "formulate_query", lambda *a, **k: "q")
    monkeypatch.setattr(assistant.websearch, "search", lambda q, n=5: [])      # 成功但查無
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    seen = {}
    _patch_common(monkeypatch, seen)
    out = assistant.compose_reply(6803, "今天股價")
    assert out == "本人回覆"                        # 查無＝不掛告警，照常回


def test_owner_search_off_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", False)        # 開關關
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    called = {"n": 0}
    monkeypatch.setattr(assistant.websearch, "formulate_query", lambda *a, **k: "q")
    monkeypatch.setattr(assistant.websearch, "search",
                        lambda q, n=5: called.__setitem__("n", 1) or [])
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(6803, "今天台股怎樣")
    assert called["n"] == 0


def test_colleague_no_search(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    called = {"n": 0}
    monkeypatch.setattr(assistant.websearch, "formulate_query", lambda *a, **k: "q")
    monkeypatch.setattr(assistant.websearch, "search",
                        lambda q, n=5: called.__setitem__("n", 1) or [])
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(999, "今天台股怎樣")            # 非 owner
    assert called["n"] == 0
