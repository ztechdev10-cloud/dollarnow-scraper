"""مراقب قنوات تلغرام لاستخراج أسعار الدولار"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
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
    MIN_DOLLAR_RATE,
    MAX_DOLLAR_RATE,
)

logger = logging.getLogger(__name__)


@dataclass
class RawRate:
    """سعر خام من مصدر واحد"""
    source: str
    buy: Optional[float]
    sell: Optional[float]
    timestamp: datetime
    reliability: float
    raw_text: str


# أنماط Regex لاستخراج الأسعار من النصوص العربية
PRICE_PATTERNS = [
    # "شراء: 13500 - بيع: 13700"
    r"شراء[:\s]*([0-9,،.]+).*?بيع[:\s]*([0-9,،.]+)",
    # "بيع: 13700 شراء: 13500"
    r"بيع[:\s]*([0-9,،.]+).*?شراء[:\s]*([0-9,،.]+)",
    # "دولار: 13600"
    r"(?:دولار|الدولار|USD)[:\s]*([0-9,،.]+)",
    # "13500/13700" (شراء/بيع)
    r"([0-9,،.]{4,6})\s*/\s*([0-9,،.]{4,6})",
    # رقم وحيد "13600 ل.س" أو "13600 ليرة"
    r"([0-9,،.]{4,6})\s*(?:ل\.?س|ليرة|SYP)",
]

# أنماط عربية للأرقام
AR_NUM_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩،", "0123456789,")


def normalize_arabic_number(text: str) -> Optional[float]:
    """حوّل الأرقام العربية والفاصلة إلى float"""
    try:
        cleaned = text.translate(AR_NUM_MAP).replace(",", "").replace("،", "")
        value = float(cleaned)
        if MIN_DOLLAR_RATE <= value <= MAX_DOLLAR_RATE:
            return value
    except (ValueError, AttributeError):
        pass
    return None


def extract_prices(text: str) -> tuple[Optional[float], Optional[float]]:
    """
    استخرج سعر الشراء والبيع من نص.
    الإرجاع: (buy, sell) - قد يكون أحدهما None
    """
    text = text.strip()

    for pattern in PRICE_PATTERNS:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            continue

        groups = match.groups()
        if len(groups) == 2:
            v1 = normalize_arabic_number(groups[0])
            v2 = normalize_arabic_number(groups[1])
            if v1 and v2:
                # الأصغر هو سعر الشراء
                return (min(v1, v2), max(v1, v2))
        elif len(groups) == 1:
            price = normalize_arabic_number(groups[0])
            if price:
                # سعر واحد نعتبره متوسطاً (نضيف هامش 0.5%)
                spread = price * 0.005
                return (round(price - spread), round(price + spread))

    return None, None


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
        """ابدأ الاستماع للقنوات"""
        await self._client.start(phone=TELEGRAM_PHONE)
        logger.info("Telegram client connected")

        # استمع للرسائل الجديدة في كل القنوات
        @self._client.on(events.NewMessage(chats=list(self._channel_map.keys())))
        async def handler(event: events.NewMessage.Event):
            await self._process_message(event.message)

        logger.info(f"Monitoring {len(self._channel_map)} Telegram channels")
        await self._client.run_until_disconnected()

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
