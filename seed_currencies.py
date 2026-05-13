"""
سكريبت لكتابة بيانات أولية لجميع العملات في Firestore.

يُشغَّل مرة واحدة للتأكد من وجود بيانات لـ EUR, TRY, SAR, JOD, XAU.
يجلب الأسعار الحقيقية من الإنترنت ثم يكتبها في Firestore.

الاستخدام:
    python seed_currencies.py
"""
import asyncio
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("seed")


async def main():
    from firebase_client import FirebaseClient
    from web_scraper import scrape_all_currencies

    logger.info("═══════════════════════════════════════════")
    logger.info("  بدء كتابة بيانات أولية لجميع العملات   ")
    logger.info("═══════════════════════════════════════════")

    firebase = FirebaseClient()

    # جلب جميع الأسعار الحالية
    logger.info("⏳ جلب أسعار اليوم من الإنترنت...")
    currency_rates = await scrape_all_currencies()

    written = 0
    for currency, rates in currency_rates.items():
        if not rates:
            logger.warning(f"⚠️  لا توجد بيانات لـ {currency}")
            continue

        # أخذ متوسط القيم المتاحة
        buys  = [r.buy  for r in rates if r.buy  and r.buy  > 0]
        sells = [r.sell for r in rates if r.sell and r.sell > 0]

        if not sells:
            logger.warning(f"⚠️  تعذّر حساب السعر لـ {currency}")
            continue

        avg_sell = sum(sells) / len(sells)
        avg_buy  = sum(buys)  / len(buys) if buys else avg_sell * 0.998

        doc_id = firebase.write_rate(
            buy           = round(avg_buy),
            sell          = round(avg_sell),
            sources_count = len(rates),
            confidence    = 80,
            change_percent = 0.0,
            currency      = currency
        )

        logger.info(f"✅ [{currency}] كُتب: بيع={round(avg_sell):,}  شراء={round(avg_buy):,}  (id={doc_id[:8]}…)")
        written += 1

    logger.info("═══════════════════════════════════════════")
    logger.info(f"  ✅ تمّت الكتابة: {written} عملة في Firestore  ")
    logger.info("═══════════════════════════════════════════")

    if written < 6:
        logger.warning("⚠️  بعض العملات لم تُكتب — تحقق من الاتصال بالإنترنت")


if __name__ == "__main__":
    asyncio.run(main())
