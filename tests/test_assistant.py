import pytest

import memory
import assistant


@pytest.fixture(autouse=True)
def _profile_no_side_effects(monkeypatch):
    # 學習畫像是 owner 私訊 side-effect（背景抽取 + 全域計數器）。預設關掉，
    # 個別測試需要時自行覆寫 prompt_block / maybe_update。避免全域計數器累積觸發真 LLM。
    assistant.user_profile.reset()
    monkeypatch.setattr(assistant.user_profile, "prompt_block", lambda pid: "")
    monkeypatch.setattr(assistant.user_profile, "maybe_update", lambda pid: None)


def _result(abstain, context="", citations=None, source_types=None):
    return type("R", (), {"abstain": abstain, "context": context,
                          "citations": citations or [],
                          "source_types": source_types or []})()


def test_colleague_no_kb_answers_best_effort(monkeypatch, tmp_path):
    # 同事問、KB 撈不到（abstain）→ 不再回固定婉拒語，改呼叫 LLM 盡力答，
    # 且 system 掛上「無 KB 盡力答、但不編造 {owner} 個人事實」守則。
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    captured = {"n": 0, "system": ""}

    def fake_generate(model, system, messages, image_bytes=None, max_output_tokens=2048):
        captured["n"] += 1
        captured["system"] = system
        return "盡力回答"

    monkeypatch.setattr(assistant, "generate", fake_generate)
    out = assistant.compose_reply(123, "不存在的問題")
    assert out == "盡力回答"                       # 不再回固定 ABSTAIN
    assert out != assistant.ABSTAIN_REPLY
    assert captured["n"] == 1                       # 有呼叫 LLM（不再早退）
    assert "絕不編造他的事" in captured["system"]   # 掛了無 KB 守則
    assert assistant.config.OWNER_NAME in captured["system"]


def test_colleague_with_kb_has_no_fallback(monkeypatch):
    # 同事問、有 KB 命中 → 照常引用，不掛無 KB 守則
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "retrieve_result",
                        lambda q, expand_graph=False: _result(False, "[來源：筆記 x]\n內容", ["筆記 x"], ["obsidian"]))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    captured = {}
    monkeypatch.setattr(assistant, "generate",
                        lambda **kw: captured.__setitem__("system", kw["system"]) or "答")
    assistant.compose_reply(123, "問題")
    assert "絕不編造他的事" not in captured["system"]


def test_owner_no_kb_uses_owner_mode_not_fallback(monkeypatch):
    # owner 私訊、KB 撈不到 → 走本人模式（不掛對外 fallback 段），且不回固定 ABSTAIN
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)
    captured = {}
    monkeypatch.setattr(assistant, "generate",
                        lambda **kw: captured.__setitem__("system", kw["system"]) or "本人回答")
    out = assistant.compose_reply(999, "我的某問題")
    assert out == "本人回答"
    assert out != assistant.ABSTAIN_REPLY
    assert "本人" in captured["system"]            # 走本人框架（build_owner_system）
    assert "覆蓋前述" not in captured["system"]     # 不掛對外無 KB fallback 段


def test_group_colleague_no_kb_has_fallback(monkeypatch):
    # 群組同事（非 owner）、無 KB → 一樣掛無 KB 守則
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    captured = {}
    monkeypatch.setattr(assistant, "generate",
                        lambda **kw: captured.__setitem__("system", kw["system"]) or "答")
    assistant.compose_reply(123, "問題", group_context="某群組近期對話")
    assert "絕不編造他的事" in captured["system"]


def test_answer_path_routes_and_calls_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "retrieve_result",
                        lambda q, expand_graph=False: _result(False, "[來源：筆記 x]\n內容", ["筆記 x"], ["obsidian"]))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    captured = {}

    def fake_choose(query, source_types=None):
        captured["source_types"] = source_types
        return "model-XYZ"

    def fake_generate(model, system, messages, image_bytes=None, max_output_tokens=2048):
        captured["model"] = model
        return "這是答案"

    monkeypatch.setattr(assistant, "choose_model", fake_choose)
    monkeypatch.setattr(assistant, "generate", fake_generate)

    out = assistant.compose_reply(123, "問題")
    assert out == "這是答案"
    assert captured["model"] == "model-XYZ"
    assert captured["source_types"] == ["obsidian"]


def test_records_and_injects_memory(monkeypatch):
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "", [], []))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "[2026-06-10 09:00] 他上次說要去東京")
    appended = []
    monkeypatch.setattr(assistant.memory, "append",
                        lambda pid, kind, content, **k: appended.append((kind, content)))
    seen = {}
    monkeypatch.setattr(assistant, "generate",
                        lambda **kw: seen.update(system=kw["system"]) or "好的")
    out = assistant.compose_reply(123, "幫我訂機票")
    assert out == "好的"
    assert "東京" in seen["system"]                      # 回想有注入 system
    assert [k for k, _ in appended] == ["user", "assistant"]   # 有記錄這輪


def test_sender_name_stored_as_alias(monkeypatch):
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "", [], []))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    aliases = []
    monkeypatch.setattr(assistant.memory, "append",
                        lambda pid, kind, content, **k: aliases.append(k.get("alias")))
    monkeypatch.setattr(assistant, "generate", lambda **kw: "好")
    assistant.compose_reply(55667788, "你好", sender_name="Mia Chen")   # 非白名單、非 owner
    assert aliases == ["Mia Chen", "Mia Chen"]          # 用 TG 顯示名當別名存起來


def test_compose_reply_expands_graph_only_owner_dm(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "generate", lambda **kw: "ok")
    seen = {}
    monkeypatch.setattr(assistant, "retrieve_result",
                        lambda q, expand_graph=False: seen.__setitem__("eg", expand_graph) or _result(True))

    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)
    assistant.compose_reply(999, "我的問題")                       # owner 私訊
    assert seen["eg"] is True
    assistant.compose_reply(123, "同事問題")                       # 同事私訊
    assert seen["eg"] is False
    assistant.compose_reply(999, "群組問題", group_context="g")    # owner 在群組
    assert seen["eg"] is False


def test_owner_no_kb_knowledge_appends_inbox_offer(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "generate", lambda **kw: "答案內容")
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: True)
    remembered = {}
    monkeypatch.setattr(assistant.inbox_capture, "remember",
                        lambda q, a: remembered.update(q=q, a=a))
    out = assistant.compose_reply(999, "ReAct 跟 Reflexion 差在哪？")
    assert out.startswith("答案內容")
    assert assistant.inbox_capture.OFFER_LINE in out
    assert remembered == {"q": "ReAct 跟 Reflexion 差在哪？", "a": "答案內容"}   # 暫存乾淨答案


def test_owner_no_kb_non_knowledge_no_offer(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "generate", lambda **kw: "嗨～")
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)
    out = assistant.compose_reply(999, "嗨")
    assert assistant.inbox_capture.OFFER_LINE not in out


def test_owner_with_kb_no_offer(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "retrieve_result",
                        lambda q, expand_graph=False: _result(False, "ctx", [], ["obsidian"]))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant, "generate", lambda **kw: "有 KB 的答案")
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: True)
    out = assistant.compose_reply(999, "某知識問題")
    assert assistant.inbox_capture.OFFER_LINE not in out          # 有 KB → 不提示


def test_colleague_no_kb_no_offer(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "generate", lambda **kw: "同事的答案")
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: True)
    out = assistant.compose_reply(123, "某知識問題")               # 非 owner
    assert assistant.inbox_capture.OFFER_LINE not in out


def test_owner_dm_injects_profile_block(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)
    monkeypatch.setattr(assistant.user_profile, "prompt_block",
                        lambda pid: "## 你對 Owner 的長期認識…\n- 偏好繁中")
    upd = {"n": 0}
    monkeypatch.setattr(assistant.user_profile, "maybe_update", lambda pid: upd.__setitem__("n", upd["n"] + 1))
    seen = {}
    monkeypatch.setattr(assistant, "generate", lambda **kw: seen.update(system=kw["system"]) or "答")
    assistant.compose_reply(999, "問題")
    assert "長期認識" in seen["system"] and "偏好繁中" in seen["system"]
    assert upd["n"] == 1                                   # 回覆後呼叫 maybe_update


def test_colleague_no_profile_injection(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)
    monkeypatch.setattr(assistant.user_profile, "prompt_block", lambda pid: "PROFILE_X")
    up = {"n": 0}
    monkeypatch.setattr(assistant.user_profile, "maybe_update", lambda pid: up.__setitem__("n", up["n"] + 1))
    seen = {}
    monkeypatch.setattr(assistant, "generate", lambda **kw: seen.update(system=kw["system"]) or "答")
    assistant.compose_reply(123, "問題")                   # 同事
    assert "PROFILE_X" not in seen["system"]
    assert up["n"] == 0                                    # 不更新同事畫像


def test_owner_group_no_profile_injection(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 999)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)
    monkeypatch.setattr(assistant.user_profile, "prompt_block", lambda pid: "PROFILE_X")
    up = {"n": 0}
    monkeypatch.setattr(assistant.user_profile, "maybe_update", lambda pid: up.__setitem__("n", up["n"] + 1))
    seen = {}
    monkeypatch.setattr(assistant, "generate", lambda **kw: seen.update(system=kw["system"]) or "答")
    assistant.compose_reply(999, "問題", group_context="g")  # owner 在群組
    assert "PROFILE_X" not in seen["system"]
    assert up["n"] == 0


def _common_mocks(monkeypatch):
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda i, st: "m")
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant, "generate", lambda **k: "乾淨答案")
    monkeypatch.setattr(assistant.inbox_capture, "is_knowledge_question", lambda t: False)


def test_search_failed_warning_not_recorded(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant.config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(assistant.config, "TAVILY_API_KEY", "k")
    monkeypatch.setattr(assistant.websearch, "looks_like_current_events", lambda t: True)
    monkeypatch.setattr(assistant.websearch, "search", lambda t: None)     # 失敗 → search_failed
    _common_mocks(monkeypatch)
    rec = {}
    monkeypatch.setattr(assistant.memory, "append",
                        lambda pid, kind, content, **k: rec.__setitem__(kind, content))
    out = assistant.compose_reply(6803, "今天台積電股價")
    assert "時事搜尋暫時不可用" in out                 # 使用者看到警語
    assert rec["assistant"] == "乾淨答案"              # 記憶只記乾淨答案（不含警語）


def test_no_search_failure_records_same(monkeypatch):
    monkeypatch.setattr(assistant.config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant.config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(assistant.config, "TAVILY_API_KEY", "k")
    monkeypatch.setattr(assistant.websearch, "looks_like_current_events", lambda t: False)  # 不觸發搜尋
    _common_mocks(monkeypatch)
    rec = {}
    monkeypatch.setattr(assistant.memory, "append",
                        lambda pid, kind, content, **k: rec.__setitem__(kind, content))
    out = assistant.compose_reply(6803, "你好嗎")
    assert "時事搜尋暫時不可用" not in out
    assert rec["assistant"] == out                    # 無警語時，記憶與回傳一致
