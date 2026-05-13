"""
سكرابر مبسّط لـ GitHub Actions — يعمل كل 30 دقيقة
يسحب الأسعار من المواقع ويكتبها في Firestore
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("github_scraper")


def init_firebase():
    import firebase_admin
    from firebase_admin import credentials, firestore as fs
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-credentials.json")
        firebase_admin.initialize_app(cred)
    return fs.client()


async def touch_all_rates_timestamp(db, now: datetime):
    """حدّث updated_at فقط لجميع العملات بدون تغيير الأسعار"""
    currencies = ["USD", "EUR", "TRY", "SAR", "JOD", "XAU"]
    for currency in currencies:
        try:
            doc_ref = db.collection("rates").document(currency)
            doc = doc_ref.get()
            if doc.exists:
                doc_ref.update({"updated_at": now})
                logger.info(f"⏰ [{currency}] تم تحديث الوقت فقط")
        except Exception as e:
            logger.warning(f"خطأ في تحديث وقت {currency}: {e}")


async def main():
    logger.info("═══════════════════════════════════════")
    logger.info("  دولار ناو — GitHub Actions Scraper   ")
    logger.info("═══════════════════════════════════════")

    now = datetime.now(timezone.utc)

    # ── تهيئة Firebase أولاً ──────────────────────────────────────────────
    db = init_firebase()

    # ── جلب الأسعار من المواقع ────────────────────────────────────────────
    from web_scraper import scrape_all_currencies
    results = await scrape_all_currencies()

    has_results = any(len(v) > 0 for v in results.values())

    if not has_results:
        logger.warning("⚠️ لم يُعثر على أي أسعار — تحديث الوقت فقط")
        await touch_all_rates_timestamp(db, now)
        logger.info("═══════════════════════════════════════")
        logger.info("  ⏰ تم تحديث الوقت بدون تغيير الأسعار ")
        logger.info("═══════════════════════════════════════")
        return

    # ── الكتابة في Firestore ──────────────────────────────────────────────
    written = 0

    for currency, rates_list in results.items():
        if not rates_list:
            continue

        rate = rates_list[-1]

        # احسب نسبة التغيير
        try:
            prev      = db.collection("rates").document(currency).get()
            prev_sell = prev.to_dict().get("sell_price", 0) if prev.exists else 0
            change    = ((rate.sell - prev_sell) / prev_sell * 100) if prev_sell else 0.0
        except Exception:
            change = 0.0

        data = {
            "currency":           currency,
            "buy_price":          round(rate.buy),
            "sell_price":         round(rate.sell),
            "change_percent":     round(change, 2),
            "sources_count":      len(rates_list),
            "confidence_percent": 90,
            "timestamp":          now,
            "updated_at":         now,
            "source":             "github_actions",
        }

        # حدّث السعر الحالي
        db.collection("rates").document(currency).set(data)

        # أضف للتاريخ
        db.collection("rates_history").add(data)

        logger.info(
            f"✅ [{currency}] بيع={round(rate.sell):,} | "
            f"شراء={round(rate.buy):,} | تغير={change:+.2f}%"
        )
        written += 1

    logger.info("═══════════════════════════════════════")
    logger.info(f"  ✅ تم تحديث {written} عملة بنجاح       ")
    logger.info("═══════════════════════════════════════")

    # ── تنظيف السجلات القديمة (كل 6 ساعات تقريباً) ───────────────────────
    if now.hour % 6 == 0 and now.minute < 35:
        await cleanup_old_history(db, now)


async def cleanup_old_history(db, now: datetime):
    """احذف سجلات rates_history الأقدم من 90 يوم"""
    cutoff = now - timedelta(days=90)
    logger.info(f"🧹 تنظيف السجلات قبل: {cutoff.strftime('%Y-%m-%d')}")

    deleted = 0
    try:
        while True:
            old_docs = (
                db.collection("rates_history")
                .where("timestamp", "<", cutoff)
                .limit(400)
                .stream()
            )
            batch  = db.batch()
            count  = 0
            for doc in old_docs:
                batch.delete(doc.reference)
                count += 1
            if count == 0:
                break
            batch.commit()
            deleted += count

        if deleted:
            logger.info(f"✅ حُذف {deleted} سجل قديم")
    except Exception as e:
        logger.warning(f"خطأ في التنظيف: {e}")


if __name__ == "__main__":
    asyncio.run(main())
