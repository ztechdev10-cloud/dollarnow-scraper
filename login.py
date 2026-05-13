"""تسجيل دخول Telegram مرة واحدة وحفظ الجلسة"""
import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE = os.environ["TELEGRAM_PHONE"]
SESSION = os.environ.get("TELEGRAM_SESSION_FILE", "sessions/telegram_session")

async def main():
    os.makedirs(os.path.dirname(SESSION), exist_ok=True)
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await client.send_code_request(PHONE)
        code = input("أدخل كود التحقق من Telegram: ")
        await client.sign_in(PHONE, code)
        print("✓ تم تسجيل الدخول بنجاح! يمكنك الآن تشغيل main.py")
    else:
        print("✓ الجلسة محفوظة مسبقاً")
    await client.disconnect()

asyncio.run(main())
