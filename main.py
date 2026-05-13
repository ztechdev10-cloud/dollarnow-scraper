"""
نقطة البدء - يشغّل كل مهام السكرابر بشكل غير متزامن

المهام:
1. مراقبة قنوات تلغرام (مستمر) — USD فقط
2. سحب المواقع كل 15 دقيقة (USD + EUR + TRY + SAR + JOD من lirat.org)
3. تجميع الأسعار وحفظها كل 5 دقائق لكل عملة
"""
import asyncio
import logging
import os
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aggregator import Aggregator, SUPPORTED_CURRENCIES
from config import WEB_SCRAPE_INTERVAL_MINUTES, LOG_LEVEL, LOG_FILE
from firebase_client import FirebaseClient
from telegram_monitor import TelegramMonitor
from web_scraper import scrape_all_currencies

# ========================
# إعداد الـ Logging
# ========================
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


async def main():
    logger.info("=== بدء تشغيل سكرابر أسعار الصرف (متعدد العملات) ===")
    logger.info(f"العملات المدعومة: {', '.join(SUPPORTED_CURRENCIES)}")

    # تهيئة المكونات
    firebase = FirebaseClient()
    aggregator = Aggregator(firebase)
    scheduler = AsyncIOScheduler(timezone="Asia/Damascus")

    # ── آخر أسعار فوركس وذهب محفوظة (لتجنّب طلبات متكررة) ──────────────
    _cached_forex: dict = {}
    _cached_gold: float | None = None

    # دالة callback تُستدعى من تلغرام (USD) — تجمع كل المصادر وتحفظ فوراً
    async def on_telegram_rate(rate):
        nonlocal _cached_forex, _cached_gold
        from web_scraper import get_forex_rates_vs_usd, get_gold_price_usd_per_oz, calculate_syp_rates
        from datetime import datetime, timezone
        from telegram_monitor import RawRate

        # 1️⃣ أضف سعر تلغرام (USD)
        aggregator.add_rate(rate, currency="USD")
        logger.info(f"📡 تلغرام → USD: بيع={rate.sell:,} | شراء={rate.buy:,}")

        # 2️⃣ احسب بقية العملات من الكاش
        try:
            if not _cached_forex:
                _cached_forex = await get_forex_rates_vs_usd()
            if _cached_gold is None:
                _cached_gold = await get_gold_price_usd_per_oz()

            syp_rates = calculate_syp_rates(rate.buy, rate.sell, _cached_forex, _cached_gold)
            now = datetime.now(timezone.utc)

            for code, (buy, sell) in syp_rates.items():
                if code == "USD":
                    continue
                aggregator.add_rate(
                    RawRate(
                        source="telegram_cross_rate",
                        buy=buy, sell=sell,
                        timestamp=now,
                        reliability=0.85,
                        raw_text=f"cross:{code}",
                    ),
                    currency=code
                )
            logger.info(f"🔄 أُعيد حساب {len(syp_rates)-1} عملة من سعر تلغرام")
        except Exception as e:
            logger.warning(f"خطأ في حساب العملات المشتقة: {e}")

        # 3️⃣ اجمع كل المصادر (تلغرام + ويب) واحفظ في Firestore فوراً
        try:
            results = aggregator.compute_and_save_all()
            for r in results:
                logger.info(
                    f"✅ [{r.currency}] بيع={r.sell:,} | شراء={r.buy:,} | "
                    f"مصادر={r.sources_count} | ثقة={r.confidence_percent}%"
                )
        except Exception as e:
            logger.warning(f"خطأ في التجميع الفوري: {e}")

    # مهمة: سحب جميع العملات من المواقع كل 15 دقيقة
    async def scrape_websites_job():
        logger.info("بدء سحب المواقع (جميع العملات)...")
        currency_rates = await scrape_all_currencies()
        total = 0
        for currency, rates in currency_rates.items():
            for rate in rates:
                aggregator.add_rate(rate, currency=currency)
            total += len(rates)
        logger.info(f"تم سحب {total} سعر من المواقع")

    # مهمة: تجميع وحفظ الأسعار كل 5 دقائق لجميع العملات
    async def aggregate_job():
        results = aggregator.compute_and_save_all()
        for result in results:
            logger.info(
                f"✓ [{result.currency}] بيع={result.sell:,} | شراء={result.buy:,} | "
                f"مصادر={result.sources_count} | ثقة={result.confidence_percent}%"
            )

    # مهمة: تحديث كاش الفوركس والذهب كل ساعة
    async def refresh_forex_cache_job():
        nonlocal _cached_forex, _cached_gold
        from web_scraper import get_forex_rates_vs_usd, get_gold_price_usd_per_oz
        _cached_forex = await get_forex_rates_vs_usd()
        _cached_gold  = await get_gold_price_usd_per_oz()
        logger.info(f"✓ تم تحديث كاش أسعار الفوركس والذهب")

    # مهمة: تنظيف البيانات القديمة مرة يومياً
    async def cleanup_job():
        logger.info("تنظيف البيانات القديمة...")
        firebase.cleanup_old_rates(days=90)

    # جدولة المهام
    scheduler.add_job(scrape_websites_job,     "interval", minutes=WEB_SCRAPE_INTERVAL_MINUTES, id="web_scrape")
    scheduler.add_job(aggregate_job,           "interval", minutes=5,  id="aggregate")
    scheduler.add_job(refresh_forex_cache_job, "interval", minutes=60, id="forex_cache")
    scheduler.add_job(cleanup_job,             "cron",     hour=2, minute=0, id="cleanup")
    scheduler.start()

    # ابدأ بسحب فوري
    await scrape_websites_job()
    await aggregate_job()

    # شغّل مراقب تلغرام (يعمل حتى الإيقاف)
    telegram = TelegramMonitor(on_rate_received=on_telegram_rate)
    try:
        await telegram.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف السكرابر...")
        scheduler.shutdown()
        await telegram.stop()


if __name__ == "__main__":
    asyncio.run(main())
