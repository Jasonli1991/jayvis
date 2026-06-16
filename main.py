import asyncio
import random
import os
import base64
from pathlib import Path
from typing import Optional

# 壓制不必要的警告
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import anthropic
from telethon import TelegramClient, events
from telethon.network import ConnectionTcpFull
from telethon.tl.types import User, Chat, Channel

import config
import memory
import guard
import persona
from rag.retriever import retrieve, retrieve_result
from github_sync import get_project_status

# ── 全域狀態 ─────────────────────────────────────────────────────────────────


def _load_weekly_focus() -> str:
    # 使用者透過控制台寫入 WeeklyFocus.md；未設定時退回 .example 範本，再退回空字串。
    _d = Path(__file__).parent / "prompts"
    for name in ("WeeklyFocus.md", "WeeklyFocus.example.md"):
        p = _d / name
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


_persona = persona.render_persona()
_weekly_focus = _load_weekly_focus()
_project_status_cache: str = ""
_project_status_ts: float = 0.0
PROJECT_STATUS_TTL = 3600


def _refresh_project_status():
    global _project_status_cache, _project_status_ts
    import time
    now = time.time()
    if not _project_status_cache or (now - _project_status_ts) > PROJECT_STATUS_TTL:
        _project_status_cache = get_project_status()
        _project_status_ts = now
    return _project_status_cache


def _build_system_prompt(rag_context: str, project_status: str) -> str:
    parts = [_persona, "\n\n" + _weekly_focus]
    if rag_context:
        parts.append("\n\n## 相關知識庫內容（供你參考，不要直接複製貼上）\n\n" + rag_context)
    if project_status:
        parts.append("\n\n" + project_status)
    return "\n".join(parts)


async def _generate_reply(claude: anthropic.Anthropic, sender_id: int, incoming: str, image_bytes: Optional[bytes] = None) -> str:
    if image_bytes:
        rag_context = ""
    else:
        result = retrieve_result(incoming)
        if result.abstain:
            reply = f"這題我手邊的資料不足，先幫你記下來，等 {config.OWNER_NAME} 回來確認再回覆你 🙏"
            memory.append(sender_id, "user", incoming)
            memory.append(sender_id, "assistant", reply)
            return reply
        rag_context = result.context

    project_status = _refresh_project_status()
    system = _build_system_prompt(rag_context, project_status)

    history = memory.get_history(sender_id)

    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode()
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": incoming if incoming else "這張圖片是什麼？"},
        ]
        memory_text = f"[圖片]{' ' + incoming if incoming else ''}"
    else:
        user_content = incoming
        memory_text = incoming

    messages = history + [{"role": "user", "content": user_content}]

    response = claude.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=300,
        system=system,
        messages=messages,
    )
    reply = response.content[0].text.strip()

    memory.append(sender_id, "user", memory_text)
    memory.append(sender_id, "assistant", reply)

    return reply


# ── 主程式 ───────────────────────────────────────────────────────────────────

async def main():
    # Client 在 async context 內初始化，確保 event loop 一致
    client = TelegramClient(
        config.TG_SESSION_NAME,
        config.TG_API_ID,
        config.TG_API_HASH,
        connection=ConnectionTcpFull,
        connection_retries=5,
        retry_delay=3,
        device_model="Desktop",
        system_version="macOS 14.0",
        app_version="1.0.0",
        lang_code="zh-tw",
    )
    claude = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # ── 事件處理器 ───────────────────────────────────────────────────────────

    @client.on(events.NewMessage(incoming=True))
    async def handle_incoming(event):
        if not config.VACATION_MODE:
            return
        # 私訊白名單：只回覆名單內的人
        if event.is_private and config.REPLY_WHITELIST_ONLY:
            if event.sender_id not in whitelist_ids:
                return
        # 群組：只在白名單群組內被 @ 才回
        if not event.is_private:
            if not event.mentioned:
                return
            if config.REPLY_WHITELIST_ONLY and event.chat_id not in whitelist_group_ids:
                return
        me = await client.get_me()
        if event.sender_id == me.id:
            return
        # 剝掉 @mention 實體，只保留真正的問題內容
        incoming_text = event.raw_text
        for _, offset, length in (
            (e.type, e.offset, e.length)
            for e in (event.message.entities or [])
            if hasattr(e, "offset")
        ):
            incoming_text = incoming_text[:offset] + incoming_text[offset + length:]
        incoming_text = incoming_text.strip()

        # 下載圖片（如果有的話）
        image_bytes = None
        if event.message.photo:
            image_bytes = await client.download_media(event.message, bytes)

        # 只有 @ 沒有內容且沒有圖片，簡短回應
        if not incoming_text and not image_bytes:
            await event.reply("哥今天請假，急事請Line聯絡，或是等我回來處理，謝謝😀")
            return

        # Prompt injection 偵測
        if guard.is_injection(incoming_text):
            await event.reply("嘿嘿抓到，你484想搞？😅")
            return

        delay = random.uniform(config.REPLY_DELAY_MIN, config.REPLY_DELAY_MAX)
        await asyncio.sleep(delay)
        async with client.action(event.chat_id, "typing"):
            reply = await _generate_reply(claude, event.sender_id, incoming_text, image_bytes)
        await event.reply(reply)

    @client.on(events.NewMessage(outgoing=True, pattern=r"^/vacation (on|off)$"))
    async def toggle_vacation(event):
        mode = event.pattern_match.group(1)
        config.VACATION_MODE = mode == "on"
        status = "✅ 請假模式已開啟" if config.VACATION_MODE else "🔕 請假模式已關閉"
        await event.reply(status)

    @client.on(events.NewMessage(outgoing=True, pattern=r"^/reindex$"))
    async def reindex(event):
        await event.reply("⏳ 重新索引知識庫中...")
        from rag.indexer import build_index
        await asyncio.get_event_loop().run_in_executor(None, build_index)
        await event.reply("✅ 索引更新完成")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^/clear_memory$"))
    async def clear_memory(event):
        memory.clear_all()
        await event.reply("🧹 所有對話記憶已清除")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^/sync_tg$"))
    async def sync_tg(event):
        await event.reply("⏳ 開始同步 TG 訊息到知識庫...")
        from tg_history_sync import sync
        await sync()
        await event.reply("✅ TG 訊息同步完成")

    # ── 啟動 ─────────────────────────────────────────────────────────────────

    await client.start()
    me = await client.get_me()

    # 啟動時解析白名單：聯絡人 + 群組名稱 → ID
    whitelist_ids: set[int] = set()
    whitelist_group_ids: set[int] = set()
    if config.REPLY_WHITELIST_ONLY:
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, User) and dialog.name in config.TG_SYNC_CONTACTS:
                whitelist_ids.add(dialog.entity.id)
            elif isinstance(dialog.entity, (Chat, Channel)) and dialog.name in config.TG_SYNC_GROUPS:
                whitelist_group_ids.add(dialog.entity.id)
        print(f"🔒 私訊白名單：{len(whitelist_ids)} 人｜群組白名單：{len(whitelist_group_ids)} 個")

    print(f"✅ 已登入：{me.first_name}（@{me.username}）")
    print(f"📌 請假模式：{'開啟' if config.VACATION_MODE else '關閉'}")
    print("指令：/vacation on｜/vacation off｜/reindex｜/sync_tg｜/clear_memory")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
