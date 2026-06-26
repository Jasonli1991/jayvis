import assistant


def test_build_owner_system_framing():
    s = assistant.build_owner_system("", "")
    assert "本人" in s                         # 本人框架
    assert "一般知識" in s                       # 可用一般知識答（不再硬性來源免責）
    assert "不要編造" in s                       # 不編造個人事實
    assert "代表他回答同事" not in s             # 不含對外代言


def test_build_owner_system_guides_code_change_flow():
    # 改某專案的請求 → 引導走「修復計畫→執行」委派流程，別丟手動步驟
    s = assistant.build_owner_system("", "")
    assert "別只丟手動步驟" in s and "修復計畫" in s


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
    monkeypatch.setattr(assistant.memory, "recent_actions", lambda *a, **k: [])
    monkeypatch.setattr(assistant.memory, "append", lambda *a, **k: None)
    monkeypatch.setattr(assistant, "_self_doc_seeded", lambda: True)   # 預設已認識自己；不灌引導語干擾既有斷言
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


def test_owner_dm_injects_recent_actions(monkeypatch):
    # owner 私訊：常駐「我最近做過的事」區塊注入 → 動作做完下一輪不忘自己做了什麼
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    monkeypatch.setattr(assistant.memory, "recent_actions",
                        lambda *a, **k: [{"ts": "2026-06-24 15:00:00",
                                          "content": "已建立『與 Max 開會』6/25 15:00"}])
    out = assistant.compose_reply(6803, "那提醒我前一天通知")
    assert out == "本人回覆"
    assert "做過的事" in seen["system"]
    assert "已建立『與 Max 開會』6/25 15:00" in seen["system"]


def test_owner_dm_guides_to_panel_when_self_doc_missing(monkeypatch):
    # 還沒「認識自己」→ owner 私訊系統提示加入「去面板按『讓 JAYVIS 認識自己』」的條件引導
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    monkeypatch.setattr(assistant, "_self_doc_seeded", lambda: False)
    assistant.compose_reply(6803, "你是誰？你能做什麼")
    assert "讓 JAYVIS 認識自己" in seen["system"] and "記憶管理" in seen["system"]


def test_owner_dm_no_guidance_when_self_doc_seeded(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)                          # 預設 _self_doc_seeded → True
    assistant.compose_reply(6803, "你能做什麼")
    assert "讓 JAYVIS 認識自己" not in seen["system"]          # 已認識自己 → 不嘮叨
    assert "群組限制" not in seen["system"]                    # 私訊不套群組收斂（私訊能力完整）
    assert "你能為同事做什麼" not in seen["system"]            # owner 不套同事界線（owner 能力完整）


def test_colleague_capability_honesty(monkeypatch):
    # 同事被問能做什麼：誠實界線——只知識問答、動作工具只服務 owner、不主打陪聊但單句閒聊仍可回
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "OWNER_NAME", "Owner")
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(999, "你能做什麼")                 # 非 owner（同事）
    assert "只服務 Owner 本人" in seen["system"]               # 動作工具 owner-only
    assert "以工作／知識問答為主" in seen["system"]
    assert "不用拒人" in seen["system"]                        # 保留：單句閒聊仍可自然回
    assert "鐵則" in seen["system"] and "不畫餅" in seen["system"]   # 不對同事承諾/列出做不到的事


def test_colleague_on_leave_can_hand_off_todos(monkeypatch):
    # owner 請假中：同事可發問＋交辦待辦，JAYVIS 會整理成「已處理＋待辦」給 owner
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "OWNER_NAME", "Owner")
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant._leave_io, "is_on_leave", lambda: True)
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(999, "Owner 在嗎")                 # 同事、請假中
    assert "請假中" in seen["system"] and "交辦" in seen["system"]
    assert "已處理＋待辦" in seen["system"]


def test_colleague_not_on_leave_no_todo_note(monkeypatch):
    # 沒請假 → 不出現請假交辦說明
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    monkeypatch.setattr(assistant._leave_io, "is_on_leave", lambda: False)
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(999, "你能做什麼")
    assert "已處理＋待辦" not in seen["system"]


def test_colleague_no_panel_guidance_even_if_unseeded(monkeypatch):
    # 同事沒有面板：就算 self-doc 沒灌也不該叫他去點面板按鈕
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    monkeypatch.setattr(assistant, "_self_doc_seeded", lambda: False)
    assistant.compose_reply(999, "你能做什麼")                 # 非 owner
    assert "讓 JAYVIS 認識自己" not in seen["system"]


def test_colleague_dm_no_recent_actions_block(monkeypatch):
    # 非 owner：不查也不注入「我最近做過的事」（同事不能做動作，且避免外洩）
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    called = {"n": 0}
    monkeypatch.setattr(assistant.memory, "recent_actions",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [])
    assistant.compose_reply(999, "嗨")                  # 非 owner
    assert "做過的事" not in seen["system"]
    assert called["n"] == 0


def test_owner_in_group_no_recent_actions(monkeypatch):
    # owner 在群組：不注入私訊動作（不外洩、群組脈絡走 group_context）
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    called = {"n": 0}
    monkeypatch.setattr(assistant.memory, "recent_actions",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [])
    assistant.compose_reply(6803, "大家好", group_context="群組脈絡")
    assert called["n"] == 0
    assert "做過的事" not in seen["system"]
    assert "同事在群組只能用知識問答" in seen["system"]      # 同事在群組只有知識問答
    assert "只有我本人能在群組觸發" in seen["system"]        # 生圖/媒體/搜尋是 owner 專屬、別講成同事也能用
    assert "同事也能丟給你" in seen["system"]                # 明確禁止把多媒體講成同事可用
    assert "冷卻約 60 分鐘" in seen["system"]               # 同事閒聊冷卻
    assert "鐵則" in seen["system"]                         # 不承諾/不自我介紹做不到的事


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


def test_colleague_no_kb_realtime_guard(monkeypatch):
    # 同事問時效性問題、KB 無、又不能搜尋 → system 帶「查不到即時、別硬給」守則，避免亂回答
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(999, "今天台積電股價多少")        # 非 owner
    assert "查不到即時資訊" in seen["system"] and "硬給" in seen["system"]


def test_owner_search_in_group_injects(monkeypatch):
    # owner 本人在群組（被 @）也能查；判斷脈絡用群組脈絡，不用私訊記憶。
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    fq = {}
    monkeypatch.setattr(assistant.websearch, "formulate_query",
                        lambda message, context="": fq.update(ctx=context) or "q")
    monkeypatch.setattr(assistant.websearch, "search",
                        lambda q, n=5: [{"title": "SpaceX 新聞", "url": "http://x", "content": "獵鷹發射成功"}])
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    out = assistant.compose_reply(6803, "今天 spaceX 新聞", group_context="群組脈絡")
    assert out == "本人回覆"
    assert "獵鷹發射成功" in seen["system"] and "http://x" in seen["system"]   # 群組也注入搜尋結果
    assert fq["ctx"] == "群組脈絡"                                            # 用群組脈絡判斷，不混入私訊記憶


def test_colleague_in_group_no_search(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", True)
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    called = {"n": 0}
    monkeypatch.setattr(assistant.websearch, "formulate_query",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "q")
    monkeypatch.setattr(assistant.websearch, "search",
                        lambda q, n=5: called.__setitem__("n", called["n"] + 1) or [])
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(False, "ctx", ["obsidian"]))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(999, "今天台股怎樣", group_context="群組脈絡")     # 同事在群組
    assert called["n"] == 0                       # 同事在群組仍不觸發搜尋


def test_owner_in_group_action_tool_guard(monkeypatch):
    # owner 在群組要求瀏覽/截圖 → system 帶「群組做不到、別假裝在處理」守則；且不誤傷生圖/搜尋
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", False)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(6803, "幫我截圖 ka2ka.com", group_context="群組脈絡")
    sys = seen["system"]
    assert "私訊" in sys and "瀏覽" in sys and "假裝" in sys      # 動作工具群組受限、別假裝在處理
    assert "生圖" in sys and "時事搜尋" in sys                    # 生圖/搜尋仍是我本人群組可用（owner 專屬），不誤傷


def test_owner_dm_no_group_guard(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    monkeypatch.setattr(config, "SEARCH_ENABLED", False)
    monkeypatch.setattr(assistant, "retrieve_result", lambda q, expand_graph=False: _result(True))
    monkeypatch.setattr(assistant.memory, "recall", lambda *a, **k: "")
    seen = {}
    _patch_common(monkeypatch, seen)
    assistant.compose_reply(6803, "幫我截圖 ka2ka.com")          # 私訊
    assert "群組限制" not in seen["system"]                       # 私訊不掛群組守則


# --- 動作工具自我認知 block ---
import assistant as _a
import config as _c


def _all_tools(monkeypatch, on):
    monkeypatch.setattr(_c, "ACTIONS_ENABLED", on)
    monkeypatch.setattr(_c, "EMAIL_ENABLED", on)
    monkeypatch.setattr(_c, "MEDIA_ENABLED", on)
    monkeypatch.setattr(_c, "SEARCH_ENABLED", on)
    monkeypatch.setattr(_c, "TAVILY_API_KEY", "k" if on else "")
    monkeypatch.setattr(_c, "IMAGE_GEN_ENABLED", on)
    monkeypatch.setattr(_c, "BROWSE_ENABLED", on)
    monkeypatch.setattr(_c, "CODE_ROOT", "/x" if on else "")
    # 真實就緒探測在單元測試中固定為「就緒」，避免依賴執行環境（macOS／郵件帳號／Chromium）
    monkeypatch.setattr(_a, "_is_macos", lambda: True)
    monkeypatch.setattr(_a, "_email_ready", lambda: True)
    monkeypatch.setattr(_a, "_browse_ready", lambda: True)


def test_action_tools_block_all_on(monkeypatch):
    _all_tools(monkeypatch, True)
    s = _a._action_tools_block()
    # 只數工具列前綴「- ✅／- ⬜」，避免被規則散文裡的符號干擾
    assert s.count("- ✅") == 7 and "- ⬜" not in s
    assert "你的動作工具" in s and "面板" in s          # 含標題與提示去面板


def test_action_tools_block_all_off(monkeypatch):
    _all_tools(monkeypatch, False)
    s = _a._action_tools_block()
    assert s.count("- ⬜") == 7 and "- ✅" not in s


def test_action_tools_search_needs_key(monkeypatch):
    _all_tools(monkeypatch, True)
    monkeypatch.setattr(_c, "TAVILY_API_KEY", "")        # 開了但沒金鑰 → 實際不可用
    s = _a._action_tools_block()
    assert "- ⬜ 時事搜尋（即時資訊）" in s
    assert s.count("- ✅") == 6


def test_action_tools_code_needs_root(monkeypatch):
    _all_tools(monkeypatch, True)
    monkeypatch.setattr(_c, "CODE_ROOT", "")             # 沒設 CODE_ROOT → 未啟用
    s = _a._action_tools_block()
    assert "- ⬜ 程式委派" in s


def test_tool_enabled_but_not_ready_shows_reason(monkeypatch):
    # 啟用但前置缺 → 顯示「⬜（已開但缺：原因）」，讓 JAYVIS 講得出為何現在做不到
    _all_tools(monkeypatch, True)
    monkeypatch.setattr(_a, "_is_macos", lambda: False)        # 行事曆：開了但非 macOS
    monkeypatch.setattr(_a, "_email_ready", lambda: False)     # 收發信：開了但沒帳號
    monkeypatch.setattr(_a, "_browse_ready", lambda: False)    # 瀏覽：開了但 Chromium 沒裝
    s = _a._action_tools_block()
    assert "⬜ 行事曆：查/排/改/刪行程（已開但缺：需 macOS" in s
    assert "⬜ 收發信（已開但缺：找不到可用的郵件帳號）" in s
    assert "⬜ 瀏覽網頁（已開但缺：Chromium 未安裝" in s
    assert "據實說那個原因" in s                                # 規則教 JAYVIS 講真實原因


def test_calendar_not_ready_on_non_macos(monkeypatch):
    _all_tools(monkeypatch, True)
    monkeypatch.setattr(_a, "_is_macos", lambda: False)
    s = _a._action_tools_block()
    assert "✅ 行事曆" not in s and "⬜ 行事曆" in s            # 非 macOS → 行事曆不可用


def test_email_readiness_probes_accounts(monkeypatch):
    # _email_ready 探測真實郵件帳號：有帳號才就緒
    _a._reset_readiness()
    import mail_tool
    monkeypatch.setattr(mail_tool, "list_accounts", lambda: ["work@x.com"])
    assert _a._email_ready() is True
    _a._reset_readiness()
    monkeypatch.setattr(mail_tool, "list_accounts", lambda: [])
    assert _a._email_ready() is False


def test_email_readiness_uses_cache_within_ttl(monkeypatch):
    # TTL 內回快取值：第一次探到 True 後，即使帳號清單變空（未 reset）仍回 True（證明走快取而非每次重探）
    _a._reset_readiness()
    import mail_tool
    monkeypatch.setattr(mail_tool, "list_accounts", lambda: ["work@x.com"])
    assert _a._email_ready() is True
    monkeypatch.setattr(mail_tool, "list_accounts", lambda: [])   # 換空，但不 reset
    assert _a._email_ready() is True                              # 仍回快取的 True


def test_browse_readiness_probes_chromium_dir(tmp_path, monkeypatch):
    # _browse_ready 的真實探測：playwright 瀏覽器目錄下有沒有 chromium-* 子目錄
    import install_manifest
    monkeypatch.setattr(install_manifest, "playwright_browsers_dir", lambda: tmp_path)
    _a._reset_readiness()
    assert _a._browse_ready() is False                            # 沒有 chromium-* → 未就緒
    (tmp_path / "chromium-1234").mkdir()
    _a._reset_readiness()
    assert _a._browse_ready() is True                             # 有 chromium-* → 就緒


def test_owner_system_includes_tools_block(monkeypatch):
    _all_tools(monkeypatch, False)
    s = _a.build_owner_system("", "")
    assert "你的動作工具" in s                  # owner 路徑含工具 block


def test_owner_system_includes_roster(monkeypatch):
    # owner 模式注入團隊/老闆/專案名冊 → 你問人員角色/職責也答得出（以前 owner 反而沒有）
    monkeypatch.setattr(_a.persona, "load_profile", lambda: {
        "owner_name": "Jason",
        "projects": [{"name": "jayvis", "desc": "TG 搭檔"}],
        "team": [{"name": "Max", "role": "後端"}],
        "bosses": [{"name": "Lin", "note": "只看結論"}]})
    s = _a.build_owner_system("", "")
    assert "你認識的人與專案" in s
    assert "Max（後端）" in s and "jayvis（TG 搭檔）" in s and "Lin（只看結論）" in s


def test_owner_system_roster_empty_when_no_profile(monkeypatch):
    monkeypatch.setattr(_a.persona, "load_profile", lambda: {})
    s = _a.build_owner_system("", "")
    assert "你認識的人與專案" not in s          # 沒名冊資料 → 不硬塞空區塊


def test_colleague_system_excludes_tools_block(monkeypatch):
    _all_tools(monkeypatch, False)
    s = _a._build_system_prompt("", "")
    assert "你的動作工具" not in s              # 同事/群組路徑不含
