"""
النماذج المشتركة — بدون تبعيات خارجية
يُستورد من هنا في web_scraper.py و telegram_monitor.py
"""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# ── نافذة أسعار الدولار المقبولة ────────────────────────────────────────────
MIN_DOLLAR_RATE = 5_000
MAX_DOLLAR_RATE = 500_000


@dataclass
class RawRate:
    """سعر خام من مصدر واحد"""
    source: str
    buy: Optional[float]
    sell: Optional[float]
    timestamp: datetime
    reliability: float
    raw_text: str


# ── أنماط Regex لاستخراج الأسعار من النصوص العربية ──────────────────────────
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

# تحويل الأرقام العربية
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
                return (min(v1, v2), max(v1, v2))
        elif len(groups) == 1:
            price = normalize_arabic_number(groups[0])
            if price:
                spread = price * 0.005
                return (round(price - spread), round(price + spread))

    return None, None
