"""
سكرابر مبسّط لـ GitHub Actions — يعمل كل 15 دقيقة
يسحب الأسعار من المواقع ويكتبها في Firestore
"""
import asyncio
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("github_scraper")


async def main():
    logger.info("═══════════════════════════════════════")
    logger.info("  دولار ناو — GitHub Actions Scraper   ")
    logger.info("═══════════════════════════════════════")

    # ── جلب الأسعار من المواقع ──
    from web_scraper import scrape_all_currencies
    results = await scrape_all_currencies()

    if not any(results.values()):
        logger.warning("⚠️ لم يُعثر على أي أسعار من الويب — سيتم الاحتفاظ بآخر الأسعار في Firestore")
        # لا نوقف العملية — نترك Firestore كما هو

    # ── الكتابة في Firestore ──
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-credentials.json")
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    now = datetime.now(timezone.utc)
    written = 0

    for currency, rates in results.items():
        if not rates:
            continue

        # خذ أفضل سعر (الأحدث)
        rate = rates[-1]

        # احسب نسبة التغيير
        prev = db.collection("rates").document(currency).get()
        prev_sell = prev.to_dict().get("sell_price", 0) if prev.exists else 0
        change = ((rate.sell - prev_sell) / prev_sell * 100) if prev_sell else 0.0

        data = {
            "currency":           currency,
            "buy_price":          round(rate.buy),
            "sell_price":         round(rate.sell),
            "change_percent":     round(change, 2),
            "sources_count":      len(rates),
            "confidence_percent": 90,
            "timestamp":          now,
            "updated_at":         now,
            "source":             "github_actions",
        }

        # حدّث السعر الحالي
        db.collection("rates").document(currency).set(data)

        # أضف للتاريخ
        db.collection("rates_history").add(data)

        logger.info(f"✅ [{currency}] بيع={round(rate.sell):,} | شراء={round(rate.buy):,} | تغير={change:.2f}%")
        written += 1

    logger.info(f"═══════════════════════════════════════")
    logger.info(f"  ✅ تم تحديث {written} عملة بنجاح       ")
    logger.info(f"═══════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
