"""
سكريبت لكتابة بيانات تاريخية محاكاة لجميع العملات (آخر 90 يوم).

يُستخدم لاختبار الرسم البياني والإحصاءات في التطبيق.
البيانات تبدأ من أسعار حقيقية اليوم وتولّد تاريخاً واقعياً بتقلبات طبيعية.

الاستخدام:
    python seed_history.py            # يكتب 90 يوم، نقطة يومية
    python seed_history.py --days 30  # آخر 30 يوم
"""
import asyncio
import logging
import random
import sys
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("seed_history")

# ── أسعار تقريبية كنقطة بداية (يُحدَّث من الإنترنت) ──────────────────────
BASE_PRICES = {
    "USD": (13_400, 13_500),   # شراء، بيع
    "EUR": (14_500, 14_700),
    "TRY": (390,    400),
    "SAR": (3_560,  3_600),
    "JOD": (18_800, 19_000),
    "XAU": (800_000, 820_000), # ذهب عيار 21 / غرام
}

# ── تقلب يومي نموذجي لكل عملة (%) ───────────────────────────────────────
DAILY_VOLATILITY = {
    "USD": 0.8,
    "EUR": 1.0,
    "TRY": 1.5,
    "SAR": 0.3,
    "JOD": 0.3,
    "XAU": 1.2,
}


def generate_history(currency: str, days: int = 90) -> list[dict]:
    """يولّد قائمة من الأسعار التاريخية الواقعية"""
    buy_base, sell_base = BASE_PRICES.get(currency, (10_000, 10_100))
    vol = DAILY_VOLATILITY.get(currency, 1.0) / 100

    records = []
    now = datetime.now(timezone.utc)

    # ابدأ من نقطة في الماضي
    sell = sell_base * (1 + random.uniform(-0.05, 0.05))
    buy  = sell * 0.998

    for day_offset in range(days, 0, -1):
        ts = now - timedelta(days=day_offset)

        # تقلب عشوائي + اتجاه طفيف
        delta = random.gauss(0, vol)
        trend = 0.0002 if currency in ("USD", "EUR") else 0.0001
        sell  = sell * (1 + delta + trend)
        buy   = sell * random.uniform(0.996, 0.999)

        # تأكد القيم معقولة
        sell = max(sell, buy_base * 0.5)

        records.append({
            "currency":           currency,
            "buy_price":          round(buy),
            "sell_price":         round(sell),
            "timestamp":          ts,
            "sources_count":      random.randint(2, 6),
            "confidence_percent": random.randint(70, 98),
            "change_percent":     round(delta * 100, 2),
        })

    return records


async def main():
    days = 90
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        if idx + 1 < len(sys.argv):
            days = int(sys.argv[idx + 1])

    from firebase_client import FirebaseClient
    firebase = FirebaseClient()
    db = firebase._db

    from config import RATES_COLLECTION

    currencies = list(BASE_PRICES.keys())
    logger.info(f"كتابة {days} يوم تاريخي لـ {len(currencies)} عملة...")

    for currency in currencies:
        records = generate_history(currency, days)
        batch   = db.batch()
        count   = 0

        for rec in records:
            doc_ref = db.collection(RATES_COLLECTION).document()
            from google.cloud import firestore as gfs
            batch.set(doc_ref, {
                **rec,
                "timestamp": rec["timestamp"],   # datetime object → Firestore Timestamp
            })
            count += 1

            # Firestore batch limit: 500 عملية
            if count % 400 == 0:
                batch.commit()
                batch = db.batch()
                logger.info(f"  [{currency}] كُتب {count} سجل...")

        batch.commit()
        logger.info(f"✅ [{currency}] {len(records)} سجل تاريخي")

    logger.info("═══════════════════════════════════════")
    logger.info(f"  ✅ تمّ: {days * len(currencies)} سجل إجمالي  ")
    logger.info("═══════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
