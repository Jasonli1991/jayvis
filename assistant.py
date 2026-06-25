import logging
import sys
import time
from pathlib import Path
from typing import Optional

import config
import memory
import inbox_capture
import user_profile
import obsidian_folders
import persona
import websearch
from panel import env_io as _leave_io
from rag.retriever import retrieve_result
from github_sync import get_project_status
from router import choose_model
from llm import generate

_log = logging.getLogger("jayvis")    # 與 bot 同名 → 進同一個 bot.log
_persona = persona.render_persona()


def _load_weekly_focus() -> str:
    # 使用者透過控制台寫入 WeeklyFocus.md；未設定時退回 .example 範本，再退回空字串。
    _d = Path(__file__).parent / "prompts"
    for name in ("WeeklyFocus.md", "WeeklyFocus.example.md"):
        p = _d / name
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


_weekly_focus = _load_weekly_focus()
_project_status_cache: str = ""
_project_status_ts: float = 0.0
PROJECT_STATUS_TTL = 3600

ABSTAIN_REPLY = f"這題我手邊的資料不足，先幫你記下來，等 {config.OWNER_NAME} 回來確認再回覆你 🙏"

_NO_KB_FALLBACK = (
    "## 知識庫沒有相關資料時（覆蓋前述「沒有就說資料不足」）\n"
    "上面沒有提供相關知識庫內容。請依下列原則盡力回覆：\n"
    "- 通用、技術、常識類問題 → 用你的一般知識與推理把問題答好、答完整、實用。\n"
    "- 但凡涉及 {owner} 的專案、決定、行程、是否在線等個人/內部事實，而你手邊沒有資料 → "
    "誠實說你沒有這項資料、可代為轉達或請對方等 {owner} 回來確認，**絕不編造他的事**。\n"
    "- 即時／時效性資訊（股價、匯率、天氣、賽果、最新新聞、近況等會變動的）→ "
    "因為你不是 {owner}，所以沒辦法使用即時資料，不要用可能過時的記憶硬給數字／結果；"
    "誠實說你查不到即時資訊，請對方直接問 {owner} 或自己查最新來源。"
)


def _refresh_project_status() -> str:
    global _project_status_cache, _project_status_ts
    now = time.time()
    if not _project_status_cache or (now - _project_status_ts) > PROJECT_STATUS_TTL:
        _project_status_cache = get_project_status()
        _project_status_ts = now
    return _project_status_cache


def _build_system_prompt(rag_context: str, project_status: str) -> str:
    parts = [_persona, "\n\n" + _weekly_focus]
    if rag_context:
        parts.append("\n\n" + obsidian_folders.prompt_legend())
        parts.append("\n\n## 相關知識庫內容（供你參考，不要直接複製貼上）\n\n" + rag_context)
    if project_status:
        parts.append("\n\n" + project_status)
    return "\n".join(parts)


_OWNER_TONE = (
    "## 語氣與個性（你的靈魂，最優先）\n"
    "你對他講話像個**幽默風趣、有台灣味、有人情味的朋友兼搭檔**，不是冷冰冰的客服，也不是醫學／百科條目。\n"
    "- 自然口語、帶點機智；可用台灣日常用語（欸／啦／先這樣／我幫你喬／這就鐵腿啦）。\n"
    "- **精簡有重點**：別動不動長篇大論、別把小事升級成最壞情境嚇人；真的需要警示才提一句、點到為止。\n"
    "- 看場合收斂：壞消息、出錯、嚴肅決策時先把事情講清楚、給安定感，幽默收一點。"
)


# --- 動作工具「真實就緒」探測：不只看開關旗標，連前置條件都查（macOS／郵件帳號／Chromium）。
#     帳號/Chromium 探測較貴 → TTL 快取，避免每則訊息都做檔案/子行程探測。 ---
_READINESS_TTL = 60.0
_readiness_cache: dict = {}        # key -> (bool, ts)


def _reset_readiness():            # 測試/設定變更用
    _readiness_cache.clear()


def _cached_ready(key, probe) -> bool:
    now = time.time()
    hit = _readiness_cache.get(key)
    if hit and (now - hit[1]) < _READINESS_TTL:
        return hit[0]
    try:
        val = bool(probe())
    except Exception:
        val = False
    _readiness_cache[key] = (val, now)
    return val


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _self_doc_seeded() -> bool:
    """KB 裡是否已灌入 JAYVIS 自我說明（manual chunks）。沒灌時 owner 問起自己 → 引導去面板按鈕。"""
    try:
        import ingest.self_doc as _sd
        return _sd.is_seeded()
    except Exception:
        return True        # 查不到就當已灌，寧可不嘮叨（避免誤引導）


def _email_ready() -> bool:        # 收發信靠 macOS Mail（osascript）→ 要真的有可用帳號
    def _probe():
        import mail_tool
        return bool(mail_tool.list_accounts())
    return _cached_ready("email", _probe)


def _browse_ready() -> bool:       # 瀏覽要 Playwright Chromium 已下載（用便宜的 glob，不啟動 playwright）
    def _probe():
        import install_manifest
        return any(install_manifest.playwright_browsers_dir().glob("chromium-*"))
    return _cached_ready("browse", _probe)


# 動作工具清單：(顯示名, 是否啟用, 前置是否就緒, 未就緒原因)。於呼叫時即時讀 config。
# 三態：啟用且就緒＝✅；沒啟用＝⬜；啟用但前置缺＝⬜（已開但缺：原因）——讓 JAYVIS 講得出「為何現在做不到」。
_ACTION_TOOLS = (
    ("行事曆：查/排/改/刪行程", lambda: config.ACTIONS_ENABLED, lambda: _is_macos(), "需 macOS（靠 AppleScript 控制日曆）"),
    ("收發信", lambda: config.EMAIL_ENABLED, lambda: _email_ready(), "找不到可用的郵件帳號"),
    ("媒體：圖片去背/轉檔/調尺寸", lambda: config.MEDIA_ENABLED, lambda: True, ""),
    ("時事搜尋（即時資訊）", lambda: config.SEARCH_ENABLED, lambda: bool(config.TAVILY_API_KEY), "缺 Tavily 金鑰"),
    ("自動配圖", lambda: config.IMAGE_GEN_ENABLED, lambda: True, ""),
    ("瀏覽網頁", lambda: config.BROWSE_ENABLED, lambda: _browse_ready(), "Chromium 未安裝（可到面板「動作工具」安裝）"),
    ("程式委派", lambda: bool(config.CODE_ROOT), lambda: True, ""),
)


def _action_tools_block() -> str:
    """owner system prompt 用：列出動作工具的「真實就緒」狀態 + 行為規則。
    狀態於呼叫時即時讀 config／探測前置（A 自我認知 + B 缺什麼/為何做不到，同一塊文字達成）。"""
    lines = []
    for name, enabled, ready, reason in _ACTION_TOOLS:
        if not enabled():
            lines.append(f"- ⬜ {name}")
        elif ready():
            lines.append(f"- ✅ {name}")
        else:
            lines.append(f"- ⬜ {name}（已開但缺：{reason}）")
    return (
        "## 你的動作工具（實際執行由系統負責，不是你在這則回覆裡自己做）\n"
        + "\n".join(lines)
        + "\n規則：\n"
        "- 動作由系統背景處理，**別在這則回覆假裝自己執行了**。\n"
        "- 工具標 ⬜ 就是現在做不到：純 ⬜＝沒開（自然提一句去控制台面板「動作工具」打開；"
        "時事搜尋要填 Tavily 金鑰、程式委派要在 .env 設 CODE_ROOT，改後需重啟 bot）；"
        "「⬜（已開但缺…）」＝已啟用但前置沒準備好，就**據實說那個原因**（如需 macOS、沒郵件帳號、Chromium 要先在面板安裝），別只說去面板開。\n"
        "- 別假裝做得到、也別每則都報菜單，只有真的相關時才提。"
    )


def build_owner_system(rag_context: str, project_status: str) -> str:
    """owner 本人模式的 system prompt：有個性(幽默/台灣味)、坦白、不對外代言、不編造個人事實。"""
    owner = config.OWNER_NAME
    head = (
        f"你是 {owner} 本人的私人 AI 搭檔（他就是本人，不是同事）。坦白、直接地幫他。\n"
        "- 知識庫／你的記憶有的 → 據實引用。\n"
        "- 知識庫沒有、但你會的 → 直接用一般知識／推理把問題答好，**不必聲明「不是從知識庫來的」這類來源免責**（他不需要被一直提醒）；只有他主動問出處時才說明。\n"
        "- 查無的個人事實（他的專案／同事／行程細節）→ 坦白說不知道，不要編造。\n"
        "- 你沒有自動上網的能力；只有當上下文出現『即時網路搜尋結果』區塊時你才有即時資料。"
        "沒有那個區塊，就**別聲稱你搜尋過、也別假裝知道即時賽果／股價／新聞**——老實說你手邊沒有即時資訊。\n"
        "- 不需對外代言、不需婉拒；繁體中文、實用導向。"
    )
    parts = [_OWNER_TONE, "\n\n" + head, "\n\n" + _action_tools_block()]
    roster = persona.roster_block()                 # 團隊/老闆/專案名冊：owner 問人員角色職責也答得出（同事模式本來就有，owner 以前反而沒有）
    if roster:
        parts.append("\n\n" + roster)
    if rag_context:
        parts.append("\n\n" + obsidian_folders.prompt_legend())
        parts.append("\n\n## 相關知識庫內容（供你參考，不要直接複製貼上）\n\n" + rag_context)
    if project_status:
        parts.append("\n\n" + project_status)
    return "\n".join(parts)


def _addressee_line(sender_id: int) -> str:
    alias = config.ALLOWLIST_ALIASES.get(sender_id, "")
    if not alias:
        return ""
    return (f"\n\n## 對話對象\n你正在回覆的同事是：{alias}。"
            f"可在開頭自然稱呼對方（例如「Hi {alias}」）。")


def _leave_status_line() -> str:
    try:
        return _leave_io.read_leave().get("status", "")
    except Exception:
        return ""


def compose_reply(sender_id: int, incoming: str, image_bytes: Optional[bytes] = None,
                  group_context: Optional[str] = None, sender_name: Optional[str] = None) -> str:
    in_group = bool(group_context)
    owner_mode = (sender_id == config.OWNER_CHAT_ID)     # 本人模式：私訊或群組皆認（用 id）
    if image_bytes:
        rag_context, source_types = "", []
    else:
        result = retrieve_result(incoming, expand_graph=(owner_mode and not in_group))
        rag_context = "" if result.abstain else result.context
        source_types = [] if result.abstain else result.source_types

    project_status = _refresh_project_status()
    if owner_mode:
        system = build_owner_system(rag_context, project_status)
    else:
        system = _build_system_prompt(rag_context, project_status) + _addressee_line(sender_id)
        ls = _leave_status_line()
        if ls:
            system += f"\n\n## {config.OWNER_NAME} 目前狀態\n{ls}"

    if owner_mode and not in_group and not _self_doc_seeded():   # 還沒「認識自己」→ 我問起自己時引導去面板灌
        system += ("\n\n（你還沒被灌入完整的自我說明。若我問起你是誰／你能做什麼／你的設定或怎麼操作，"
                   "而你只能憑人設與工具清單粗略回答 → 就自然提一句：到控制台「記憶管理」按一下"
                   "「讓 JAYVIS 認識自己」，你就能完整、準確地說明自己。這是給我本人的提示，別每則都講、也別對外提。）")

    if owner_mode and not in_group:                 # 學習畫像只在 owner 私訊注入
        _blk = user_profile.prompt_block(sender_id)
        if _blk:
            system += "\n\n" + _blk

    if owner_mode and in_group:                     # 群組裡動作工具受限 → 誠實說，別假裝在執行
        system += (
            "\n\n## 群組限制（重要）\n"
            "你現在在群組裡。瀏覽網站／截圖、行事曆、收發／讀信、程式委派、深度分析這些動作"
            "只有在私訊我時才能執行，群組裡一律做不到。若我在群組要求這類動作，請誠實說這個要"
            "私訊才能做、請我改用私訊，**絕對不要假裝你正在處理、排隊或稍後通知**。"
            "（生圖、圖片去背／轉檔、時事查詢在群組可以正常用。）")

    # 同事（非 owner）且本輪無 KB 命中 → 覆蓋 persona「沒有就說資料不足」，改為盡力答但不編造個人事實
    if not owner_mode and not rag_context:
        system += "\n\n" + _NO_KB_FALLBACK.format(owner=config.OWNER_NAME)

    # owner：由 LLM 判斷該不該查（formulate_query）→ 要查才打 Tavily，把結果餵進 system。
    # 私訊或群組（owner 被 @）皆可，僅限本人。群組用群組脈絡判斷，避免私訊記憶混入搜尋。
    search_failed = False
    if owner_mode and config.SEARCH_ENABLED and config.TAVILY_API_KEY:
        if in_group:
            _sctx = group_context or ""
        else:
            _sctx = "\n".join(f"{'我' if t.get('role') == 'user' else '搭檔'}："
                              f"{(t.get('content') or '')[:100]}" for t in memory.recent(sender_id)[-6:])
        query = websearch.formulate_query(incoming, _sctx)
        if query:                                 # LLM 認為需要查 → 才搜
            hits = websearch.search(query)
            if hits is None:                      # 額度用完／連線失敗 → 明確告知（不靜默誤導）
                search_failed = True
                _log.info("🔎 搜尋「%s」→ 失敗（額度/連線）", query[:40])
            else:
                _log.info("🔎 搜尋「%s」→ %d 筆", query[:40], len(hits))
                if hits:
                    block = "\n".join(f"- {h['title']}（{h['url']}）\n  {h['content']}" for h in hits)
                    system += ("\n\n## 即時網路搜尋結果（時事請據此回答，務必標出來源網址；"
                               f"若與你的知識牴觸以此為準）\n{block}")

    if in_group:
        system += ("\n\n## 群組近期對話（僅背景輔助，不是答題依據）\n"
                   "**以當前這則 @ 你的訊息為主、準確回答它**；下面只是背景脈絡，"
                   "別被舊話題帶走、也別硬把不相關的內容兜進答案。\n" + group_context)

    # 群組模式：脈絡走 group_context，不混入也不污染 per-人私訊記憶（owner 在群組也不 recall → 私事不外洩）
    if in_group:
        history = []
        recall_used = False
    else:
        history = memory.recent(sender_id)
        if owner_mode:                                  # 常駐「我最近做過的事」：動作/媒體不進對話歷史，
            acts = memory.recent_actions(sender_id)     # 否則做完下一輪就忘了自己剛做什麼 → 體感換了個人
            _hist = {(t.get("content") or "") for t in history}   # 已在對話歷史出現的（寫入型動作結果會同時是 assistant turn）→ 不重複注入
            acts = [a for a in acts if a["content"] not in _hist]
            if acts:
                _lines = "\n".join(f"[{a['ts']}] {a['content']}" for a in acts)
                system += (f"\n\n## 你最近幫 {config.OWNER_NAME} 做過的事（依時間，供你自然延續；"
                           f"別重做、也別否認做過）\n{_lines}")
        recalled = memory.recall(sender_id, incoming, owner=owner_mode)
        recall_used = bool(recalled)
        if recalled:
            alias = config.ALLOWLIST_ALIASES.get(sender_id) or (config.OWNER_NAME if owner_mode else None) or sender_name or "對方"
            system += f"\n\n## 你與 {alias} 的過往記憶（供你自然延續，含時間）\n{recalled}"
    messages = history + [{"role": "user", "content": incoming or "（圖片）"}]

    model = choose_model(incoming, source_types)
    _log.info("🧠 compose %s｜model=%s｜RAG=%s｜回想=%s｜歷史%d輪%s",
              "owner" if owner_mode else "同事", model,
              "命中" if rag_context else "無", "有" if recall_used else "無",
              len(history) // 2, "｜搜尋失敗" if search_failed else "")
    reply = generate(model=model, system=system, messages=messages,
                     image_bytes=image_bytes, max_output_tokens=2048)
    # reply 此時是 LLM 乾淨答案 —— 記憶/Inbox 都用這版（暫時性錯誤警語只給使用者看）

    if not in_group:
        alias = config.ALLOWLIST_ALIASES.get(sender_id) or (
            config.OWNER_NAME if sender_id == config.OWNER_CHAT_ID else None) or sender_name
        memory_text = incoming if not image_bytes else f"[圖片]{' ' + incoming if incoming else ''}"
        memory.append(sender_id, "user", memory_text, alias=alias)
        memory.append(sender_id, "assistant", reply, alias=alias)      # 乾淨答案，不含警語

    if owner_mode and not in_group:
        user_profile.maybe_update(sender_id)            # 每 6 輪背景更新學習畫像

    # owner 私訊問到 KB 沒有的知識型問題 → 附一句「要不要記進 Obsidian Inbox」並暫存
    offer = (owner_mode and not in_group and not image_bytes and not rag_context
             and inbox_capture.is_knowledge_question(incoming))
    if offer:
        inbox_capture.remember(incoming, reply)         # 暫存「乾淨」答案

    # 以下只組「回傳給使用者」的版本：暫時性錯誤警語 + Inbox 提示，皆不入庫
    if search_failed:                             # 固定句子保證告知（不靠 LLM 自覺）
        reply = ("⚠️ 時事搜尋暫時不可用（可能 Tavily 額度用完或連線問題），"
                 "以下用我自己的知識回答、可能不是最新：\n\n" + reply)
    if offer:
        reply = reply + inbox_capture.OFFER_LINE        # 使用者看到的才附提示
    return reply
