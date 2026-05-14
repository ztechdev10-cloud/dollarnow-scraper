"""مراقب قنوات تلغرام لاستخراج أسعار الدولار"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.types import Message

from config import (
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_CHANNELS,
    TELEGRAM_PHONE,
    TELEGRAM_SESSION_FILE,
)
from models import RawRate, extract_prices, MIN_DOLLAR_RATE, MAX_DOLLAR_RATE

logger = logging.getLogger(__name__)


class TelegramMonitor:
    def __init__(self, on_rate_received):
        """
        on_rate_received: callback يُستدعى عند استخراج سعر جديد
        يستقبل RawRate
        """
        self._client = TelegramClient(
            TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH
        )
        self._on_rate_received = on_rate_received
        self._channel_map = {ch["username"]: ch for ch in TELEGRAM_CHANNELS}

    async def start(self):
        """ابدأ الاستماع للقنوات — مع إعادة الاتصال التلقائية عند الانقطاع"""

        # سجّل المعالج مرة واحدة فقط (يبقى صالحاً عبر إعادات الاتصال)
        @self._client.on(events.NewMessage(chats=list(self._channel_map.keys())))
        async def handler(event: events.NewMessage.Event):
            await self._process_message(event.message)

        retry_delay = 10  # ثانية — يزيد تدريجياً حتى 120 ثانية

        while True:
            try:
                if not self._client.is_connected():
                    await self._client.start(phone=TELEGRAM_PHONE)
                    logger.info("✅ Telegram client connected")
                    retry_delay = 10  # أعد ضبط الانتظار بعد نجاح الاتصال

                logger.info(f"📡 Monitoring {len(self._channel_map)} Telegram channels")
                await self._client.run_until_disconnected()
                logger.warning("⚠️ Telegram disconnected unexpectedly — will reconnect...")

            except (ConnectionError, OSError) as e:
                logger.warning(f"🔌 Telegram connection error: {e}")
            except asyncio.CancelledError:
                logger.info("Telegram monitor cancelled — stopping")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected Telegram error: {e}")

            logger.info(f"🔄 Reconnecting in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(int(retry_delay * 1.5), 120)  # زيادة تدريجية حتى 120 ثانية

    async def _process_message(self, message: Message):
        """معالجة رسالة واستخراج السعر منها"""
        if not message.text:
            return

        # احصل على اسم القناة
        chat = await message.get_chat()
        username = getattr(chat, "username", None)
        if username not in self._channel_map:
            return

        channel_info = self._channel_map[username]
        buy, sell = extract_prices(message.text)

        if buy is None and sell is None:
            return  # لا يوجد سعر في هذه الرسالة

        rate = RawRate(
            source=f"telegram_{username}",
            buy=buy,
            sell=sell,
            timestamp=message.date.replace(tzinfo=timezone.utc),
            reliability=channel_info["reliability"],
            raw_text=message.text[:200],
        )

        logger.info(f"Rate from @{username}: buy={buy}, sell={sell}")
        await self._on_rate_received(rate)

    async def stop(self):
        await self._client.disconnect()
        logger.info("Telegram client disconnected")
