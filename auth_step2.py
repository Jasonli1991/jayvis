import asyncio, sys, json
from telethon import TelegramClient
from telethon.network import ConnectionTcpFull
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv
import os

load_dotenv()

async def step2(code):
    with open("/tmp/tg_auth.json") as f:
        data = json.load(f)

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
    try:
        me = await c.sign_in(data["phone"], code, phone_code_hash=data["hash"])
        print(f"✅ 登入成功：{me.first_name} (@{me.username})")
        print("現在可以執行 python main.py 啟動 bot")
    except SessionPasswordNeededError:
        pwd = input("需要 2FA 密碼：")
        me = await c.sign_in(password=pwd)
        print(f"✅ 登入成功：{me.first_name} (@{me.username})")
        print("現在可以執行 python main.py 啟動 bot")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
    finally:
        await c.disconnect()

if len(sys.argv) < 2:
    print("用法：python auth_step2.py <驗證碼>")
    sys.exit(1)

asyncio.run(step2(sys.argv[1]))
