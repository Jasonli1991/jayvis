import types

import assistant


def _patch_common(monkeypatch, abstain):
    """共用：mock 檢索、模型、外部相依，回傳記錄呼叫的 dict。"""
    rec = {"generate_called": False, "memory_appends": 0, "system": "", "messages": None}

    res = types.SimpleNamespace(abstain=abstain, context="KB內容" if not abstain else "",
                                source_types=["obsidian"] if not abstain else [])
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: res)
    monkeypatch.setattr(assistant, "_refresh_project_status", lambda: "")
    monkeypatch.setattr(assistant, "_leave_status_line", lambda: "")
    monkeypatch.setattr(assistant, "choose_model", lambda incoming, st: "test-model")

    def _gen(model, system, messages, image_bytes=None, max_output_tokens=2048):
        rec["generate_called"] = True
        rec["system"] = system
        rec["messages"] = messages
        return "模型回覆"
    monkeypatch.setattr(assistant, "generate", _gen)
    monkeypatch.setattr(assistant.memory, "append",
                        lambda *a, **k: rec.__setitem__("memory_appends", rec["memory_appends"] + 1))
    monkeypatch.setattr(assistant.memory, "get_history", lambda sid: [])
    return rec


def test_group_relaxes_abstain(monkeypatch):
    """群組有上下文時，知識庫沒命中也照樣生成（不回 ABSTAIN）。"""
    rec = _patch_common(monkeypatch, abstain=True)
    out = assistant.compose_reply(111, "你覺得呢?", group_context="Alice：在討論錢包\nBob：等審核")
    assert rec["generate_called"] is True
    assert out == "模型回覆"
    assert out != assistant.ABSTAIN_REPLY


def test_group_injects_transcript_and_skips_personal_memory(monkeypatch):
    rec = _patch_common(monkeypatch, abstain=False)
    assistant.compose_reply(111, "projx 進度?", group_context="Alice：錢包\nBob：審核")
    assert "群組近期對話" in rec["system"]
    assert "Alice：錢包" in rec["system"]          # transcript 注入 system
    assert rec["memory_appends"] == 0              # 群組模式不寫私訊記憶


def test_private_colleague_no_kb_best_effort_and_writes_memory(monkeypatch):
    """私訊同事、KB 無命中：改為盡力答（呼叫 generate），仍寫私訊記憶。"""
    rec = _patch_common(monkeypatch, abstain=True)
    monkeypatch.setattr(assistant.memory, "recent", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    out = assistant.compose_reply(111, "隨便問", group_context=None)
    assert out == "模型回覆"                        # 不再回 ABSTAIN
    assert out != assistant.ABSTAIN_REPLY
    assert rec["generate_called"] is True
    assert "絕不編造他的事" in rec["system"]         # 掛無 KB 守則
    assert rec["memory_appends"] == 2              # user + assistant 各一
