import asyncio
import os
from datetime import datetime, timedelta, timezone

import chromadb
from chromadb.utils import embedding_functions
from telethon import TelegramClient
from telethon.network import ConnectionTcpFull
from telethon.tl.types import User
from dotenv import load_dotenv

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
load_dotenv()

from config import (
    TG_API_ID, TG_API_HASH, TG_SESSION_NAME,
    CHROMA_PATH, TG_SYNC_GROUPS, TG_SYNC_CONTACTS, TG_SYNC_DAYS,
)

MESSAGES_PER_CHUNK = 40  # 每個向量塊包含幾則訊息


def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_or_create_collection("knowledge_base", embedding_function=ef)


def _name_matches(dialog_name: str, targets: list[str]) -> bool:
    name = dialog_name.lower()
    return any(t.lower() in name for t in targets)


async def sync():
    since = datetime.now(timezone.utc) - timedelta(days=TG_SYNC_DAYS)
    col = _get_collection()

    tg = TelegramClient(
        TG_SESSION_NAME,
        TG_API_ID,
        TG_API_HASH,
        connection=ConnectionTcpFull,
        device_model="Desktop",
        system_version="macOS 14.0",
        app_version="1.0.0",
    )
    await tg.connect()
    me = await tg.get_me()
    print(f"已登入：{me.first_name}，開始同步最近 {TG_SYNC_DAYS} 天的 TG 訊息...\n")

    total_chunks = 0

    async for dialog in tg.iter_dialogs():
        name = dialog.name or ""
        entity = dialog.entity

        is_group = _name_matches(name, TG_SYNC_GROUPS)
        is_contact = isinstance(entity, User) and _name_matches(name, TG_SYNC_CONTACTS)

        if not is_group and not is_contact:
            continue

        source_type = "tg_group" if is_group else "tg_dm"
        print(f"  同步 [{source_type}] {name} ...", end=" ", flush=True)

        # 從最新往舊抓，遇到超出時間範圍就停
        messages = []
        async for msg in tg.iter_messages(entity):
            if not msg.date or msg.date < since:
                break
            text = (msg.raw_text or "").strip()
            if not text:
                continue
            sender = await msg.get_sender()
            sender_name = getattr(sender, "first_name", "") or name
            if getattr(sender, "last_name", None):
                sender_name += f" {sender.last_name}"
            date_str = msg.date.astimezone().strftime("%m/%d %H:%M")
            messages.append(f"[{date_str}] {sender_name}: {text}")

        if not messages:
            print("（無新訊息）")
            continue

        # 反轉為時間正序，再按塊切割存入 ChromaDB
        messages.reverse()
        chunks_written = 0
        for i in range(0, len(messages), MESSAGES_PER_CHUNK):
            chunk_text = f"【{name}】近期對話紀錄\n\n" + "\n".join(messages[i:i + MESSAGES_PER_CHUNK])
            doc_id = f"{source_type}/{name}/chunk{i // MESSAGES_PER_CHUNK}"
            col.upsert(
                ids=[doc_id],
                documents=[chunk_text],
                metadatas=[{
                    "source": f"{source_type}/{name}",
                    "type": source_type,
                    "synced_at": datetime.now().isoformat(),
                }],
            )
            chunks_written += 1

        total_chunks += chunks_written
        print(f"{len(messages)} 則 → {chunks_written} 塊")

    await tg.disconnect()
    print(f"\n✅ TG 訊息同步完成，共寫入 {total_chunks} 塊到知識庫")


if __name__ == "__main__":
    asyncio.run(sync())
