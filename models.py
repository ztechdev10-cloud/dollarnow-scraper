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
MAX_DOLLAR_RATE = 1_000_000


@dataclass
class RawRate:
    """سعر خام من مصدر واحد"""
    source: str
    buy: Optional[float]
    sell: Optional[float]
    timestamp: datetime
    reliability: float
    raw_text: str


# ── تحويل الأرقام العربية ────────────────────────────────────────────────────
AR_NUM_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩،", "0123456789,")


def normalize_arabic_number(text: str) -> Optional[float]:
    """حوّل الأرقام العربية والفاصلة إلى float"""
    try:
        cleaned = text.translate(AR_NUM_MAP).replace(",", "").replace("،", "").replace(" ", "").replace(".", "")
        value = float(cleaned)
        if MIN_DOLLAR_RATE <= value <= MAX_DOLLAR_RATE:
            return value
    except (ValueError, AttributeError):
        pass
    return None


# ── أنماط Regex لاستخراج الأسعار من النصوص العربية ──────────────────────────
# الترتيب مهم — الأكثر دقة أولاً
PRICE_PATTERNS = [
    # "شراء: 13,500 | بيع: 13,700" أو "شراء 13500 بيع 13700"
    (r"شراء[:\s،|]+([٠-٩\d,،. ]+?)[\s|،\-]+بيع[:\s،|]+([٠-٩\d,،. ]+)", "buy_sell"),
    # "بيع: 13,700 | شراء: 13,500"
    (r"بيع[:\s،|]+([٠-٩\d,،. ]+?)[\s|،\-]+شراء[:\s،|]+([٠-٩\d,،. ]+)", "sell_buy"),
    # "Buy: 13500 Sell: 13700" (English)
    (r"buy[:\s]+([0-9,. ]+?)[\s|,\-]+sell[:\s]+([0-9,. ]+)", "buy_sell_en"),
    # "Sell: 13700 Buy: 13500" (English)
    (r"sell[:\s]+([0-9,. ]+?)[\s|,\-]+buy[:\s]+([0-9,. ]+)", "sell_buy_en"),
    # "13500 / 13700" أو "13500/13700" (شراء/بيع)
    (r"([٠-٩\d][٠-٩\d,،.]{3,})\s*/\s*([٠-٩\d][٠-٩\d,،.]{3,})", "slash"),
    # "13500 - 13700" (نطاق)
    (r"([٠-٩\d][٠-٩\d,،.]{3,})\s*[-–]\s*([٠-٩\d][٠-٩\d,،.]{3,})", "range"),
    # "دولار: 13600" أو "الدولار 13600" أو "USD: 13600"
    (r"(?:دولار|الدولار|USD|usd)[:\s،]+([٠-٩\d][٠-٩\d,،.]{3,})", "single_usd"),
    # "سعر الدولار اليوم 13600"
    (r"سعر[^0-9٠-٩]{1,20}([٠-٩\d][٠-٩\d,،.]{3,})", "single_price"),
    # "13600 ل.س" أو "13600 ليرة" أو "13600 SYP"
    (r"([٠-٩\d][٠-٩\d,،.]{3,})\s*(?:ل\.?س|ليرة|SYP|syp)", "syp_suffix"),
    # رقم مجرد بين 10000 و 999999 (آخر حل)
    (r"\b([1-9][0-9]{4,5})\b", "bare_number"),
]


def extract_prices(text: str) -> tuple[Optional[float], Optional[float]]:
    """
    استخرج سعر الشراء والبيع من نص.
    الإرجاع: (buy, sell) - قد يكون أحدهما None
    """
    if not text:
        return None, None

    text = text.strip()

    for pattern, mode in PRICE_PATTERNS:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            continue

        groups = match.groups()

        if len(groups) == 2:
            v1 = normalize_arabic_number(groups[0])
            v2 = normalize_arabic_number(groups[1])
            if v1 and v2 and abs(v1 - v2) / max(v1, v2) < 0.1:  # الفرق < 10%
                if mode in ("buy_sell", "buy_sell_en", "slash", "range"):
                    return (min(v1, v2), max(v1, v2))
                else:  # sell_buy
                    return (min(v1, v2), max(v1, v2))

        elif len(groups) == 1:
            price = normalize_arabic_number(groups[0])
            if price:
                spread = price * 0.008  # هامش 0.8%
                return (round(price - spread), round(price + spread))

    return None, None
