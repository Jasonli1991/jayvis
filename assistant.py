import logging
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
import image_gen
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
    "誠實說你沒有這項資料、可代為轉達或請對方等 {owner} 回來確認，**絕不編造他的事**。"
)

_IMG_INSTRUCTION = (
    "## 需要時可配圖\n"
    "若這題配一張圖會更清楚或更生動（使用者要圖、描述視覺場景/物件/示意等），"
    "在回覆『最後獨立一行』加上 `[[圖：<簡短英文描述>]]`（用英文，Pollinations 對英文最準）。"
    "只在真的有幫助時加、一則最多一張、不確定就不要加。這個標記不會顯示給使用者。"
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


def build_owner_system(rag_context: str, project_status: str) -> str:
    """owner 本人模式的 system prompt：坦白、不對外代言、可用一般知識但註明來源、不編造個人事實。"""
    owner = config.OWNER_NAME
    head = (
        f"你是 {owner} 本人的私人 AI 助理（他就是本人，不是同事）。坦白、直接地幫他。\n"
        "- 知識庫／你的記憶有的 → 據實引用。\n"
        "- 知識庫沒有、但你會的 → 可用一般知識／推理幫忙，但要明講「這不是從你的知識庫來的」。\n"
        "- 查無的個人事實（他的專案／同事／行程細節）→ 坦白說不知道，不要編造。\n"
        "- 不需對外代言、不需婉拒；繁體中文、實用導向。"
    )
    parts = [head]
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

    if owner_mode and not in_group:                 # 學習畫像只在 owner 私訊注入
        _blk = user_profile.prompt_block(sender_id)
        if _blk:
            system += "\n\n" + _blk
        if config.IMAGE_GEN_ENABLED:                # 自動配圖能力只在 owner 私訊啟用
            system += "\n\n" + _IMG_INSTRUCTION

    # 同事（非 owner）且本輪無 KB 命中 → 覆蓋 persona「沒有就說資料不足」，改為盡力答但不編造個人事實
    if not owner_mode and not rag_context:
        system += "\n\n" + _NO_KB_FALLBACK.format(owner=config.OWNER_NAME)

    # owner 私訊問時事（關鍵詞觸發）→ 先 Tavily 搜尋，把結果餵進 system。僅 owner 私訊。
    search_failed = False
    if (owner_mode and not in_group and config.SEARCH_ENABLED and config.TAVILY_API_KEY
            and websearch.looks_like_current_events(incoming)):
        hits = websearch.search(incoming)
        if hits is None:                          # 額度用完／連線失敗 → 明確告知（不靜默誤導）
            search_failed = True
            _log.info("🔎 搜尋時事：%s → 失敗（額度/連線）", (incoming or "")[:30])
        else:
            _log.info("🔎 搜尋時事：%s → %d 筆", (incoming or "")[:30], len(hits))
            if hits:
                block = "\n".join(f"- {h['title']}（{h['url']}）\n  {h['content']}" for h in hits)
                system += ("\n\n## 即時網路搜尋結果（時事請據此回答，務必標出來源網址；"
                           f"若與你的知識牴觸以此為準）\n{block}")

    if in_group:
        system += f"\n\n## 群組近期對話（供你理解討論脈絡）\n{group_context}"

    # 群組模式：脈絡走 group_context，不混入也不污染 per-人私訊記憶（owner 在群組也不 recall → 私事不外洩）
    if in_group:
        history = []
    else:
        history = memory.recent(sender_id)
        recalled = memory.recall(sender_id, incoming, owner=owner_mode)
        if recalled:
            alias = config.ALLOWLIST_ALIASES.get(sender_id) or (config.OWNER_NAME if owner_mode else None) or sender_name or "對方"
            system += f"\n\n## 你與 {alias} 的過往記憶（供你自然延續，含時間）\n{recalled}"
    messages = history + [{"role": "user", "content": incoming or "（圖片）"}]

    model = choose_model(incoming, source_types)
    reply = generate(model=model, system=system, messages=messages,
                     image_bytes=image_bytes, max_output_tokens=2048)
    # reply 可能含 [[圖：...]] 配圖標記；入庫/Inbox 一律用剝除標記後的乾淨版（回傳值仍保留標記給 bot）
    clean = image_gen.split_marker(reply)[0]

    if not in_group:
        alias = config.ALLOWLIST_ALIASES.get(sender_id) or (
            config.OWNER_NAME if sender_id == config.OWNER_CHAT_ID else None) or sender_name
        memory_text = incoming if not image_bytes else f"[圖片]{' ' + incoming if incoming else ''}"
        memory.append(sender_id, "user", memory_text, alias=alias)
        memory.append(sender_id, "assistant", clean, alias=alias)      # 乾淨答案，不含標記/警語

    if owner_mode and not in_group:
        user_profile.maybe_update(sender_id)            # 每 6 輪背景更新學習畫像

    # owner 私訊問到 KB 沒有的知識型問題 → 附一句「要不要記進 Obsidian Inbox」並暫存
    offer = (owner_mode and not in_group and not image_bytes and not rag_context
             and inbox_capture.is_knowledge_question(incoming))
    if offer:
        inbox_capture.remember(incoming, clean)         # 暫存「乾淨」答案（不含標記）

    # 以下只組「回傳給使用者」的版本：暫時性錯誤警語 + Inbox 提示，皆不入庫
    if search_failed:                             # 固定句子保證告知（不靠 LLM 自覺）
        reply = ("⚠️ 時事搜尋暫時不可用（可能 Tavily 額度用完或連線問題），"
                 "以下用我自己的知識回答、可能不是最新：\n\n" + reply)
    if offer:
        reply = reply + inbox_capture.OFFER_LINE        # 使用者看到的才附提示
    return reply
