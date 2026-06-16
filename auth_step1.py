import asyncio
from telethon import TelegramClient
from telethon.network import ConnectionTcpFull
from dotenv import load_dotenv
import os, json

load_dotenv()
PHONE = os.getenv("TG_PHONE", "")   # 你的 Telegram 手機號（含國碼，如 +1234567890）

async def step1():
    c = TelegramClient(
        os.getenv("TG_SESSION_NAME", "jayvis_session"),
        int(os.getenv("TG_API_ID")),
        os.getenv("TG_API_HASH"),
        connection=ConnectionTcpFull,
        device_model="Desktop",
        system_version="macOS 14.0",
        app_version="1.0.0",
    )
    await c.connect()
    result = await c.send_code_request(PHONE)
    data = {"phone": PHONE, "hash": result.phone_code_hash}
    with open("/tmp/tg_auth.json", "w") as f:
        json.dump(data, f)
    await c.disconnect()
    print("✅ 驗證碼已發送到你的 TG app")
    print("收到驗證碼後執行：python auth_step2.py <驗證碼>")

asyncio.run(step1())
