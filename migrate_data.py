"""
سكربت ترحيل البيانات من الهيكل القديم إلى الجديد.

الهيكل القديم:  rates/{auto_id}  {currency: "USD", ...}
الهيكل الجديد:  rates/USD        {buy_price, sell_price, ...}
                rates_history/{auto_id}  (السجل التاريخي)

الاستخدام:
    python migrate_data.py
"""
import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("migrate")

CURRENCIES = ["USD", "EUR", "TRY", "SAR", "JOD", "XAU"]


def migrate():
    # ── تهيئة Firebase ───────────────────────────────────────────────────────
    try:
        from firebase_client import FirebaseClient
        fc = FirebaseClient()
        db = fc._db
    except Exception as e:
        logger.error(f"فشل الاتصال بـ Firebase: {e}")
        sys.exit(1)

    logger.info("═══════════════════════════════════════════")
    logger.info("   بدء ترحيل البيانات — دولار ناو         ")
    logger.info("═══════════════════════════════════════════\n")

    # ── قراءة كل documents القديمة ──────────────────────────────────────────
    logger.info("📖 قراءة البيانات القديمة من rates...")
    old_docs = list(db.collection("rates").stream())
    logger.info(f"   وُجد {len(old_docs)} document\n")

    if not old_docs:
        logger.warning("لا توجد بيانات للترحيل — الانتهاء.")
        return

    # ── تصنيف: تاريخي + أحدث سعر لكل عملة ─────────────────────────────────
    all_history     = []
    latest_by_curr  = {}
    skipped         = 0

    for doc in old_docs:
        data     = doc.to_dict()
        currency = data.get("currency")

        # تجاهل documents الثابتة الموجودة مسبقاً (USD, EUR, ...)
        if doc.id in CURRENCIES:
            logger.info(f"   ← تجاهل document ثابت: {doc.id}")
            skipped += 1
            continue

        if not currency or currency not in CURRENCIES:
            continue

        all_history.append(data)

        def ts_to_seconds(ts):
            if ts is None: return 0
            if hasattr(ts, "seconds"): return ts.seconds        # Firestore Timestamp
            if hasattr(ts, "timestamp"): return ts.timestamp()  # datetime
            return 0

        curr_ts = ts_to_seconds(latest_by_curr.get(currency, {}).get("timestamp"))
        new_ts  = ts_to_seconds(data.get("timestamp"))
        if currency not in latest_by_curr or new_ts > curr_ts:
            latest_by_curr[currency] = data

    logger.info(f"✅ عملات فريدة: {list(latest_by_curr.keys())}")
    logger.info(f"📦 سجلات تاريخية: {len(all_history)}")
    logger.info(f"⏭  تم تجاهل: {skipped} document ثابت\n")

    # ── نقل التاريخ إلى rates_history ───────────────────────────────────────
    if all_history:
        logger.info("📤 نقل السجل التاريخي إلى rates_history...")
        batch_size = 400
        total = 0
        for i in range(0, len(all_history), batch_size):
            batch = db.batch()
            for rec in all_history[i:i+batch_size]:
                ref = db.collection("rates_history").document()
                batch.set(ref, rec)
                total += 1
            batch.commit()
            logger.info(f"   نُقل {total}/{len(all_history)}")
        logger.info(f"✅ اكتمل نقل {total} سجل تاريخي\n")

    # ── حذف documents القديمة (غير الثابتة) ─────────────────────────────────
    to_delete = [d for d in old_docs if d.id not in CURRENCIES]
    if to_delete:
        logger.info(f"🗑  حذف {len(to_delete)} document قديم من rates...")
        batch_size = 400
        deleted = 0
        for i in range(0, len(to_delete), batch_size):
            batch = db.batch()
            for doc in to_delete[i:i+batch_size]:
                batch.delete(doc.reference)
                deleted += 1
            batch.commit()
            logger.info(f"   حُذف {deleted}/{len(to_delete)}")
        logger.info(f"✅ اكتمل الحذف\n")

    # ── إنشاء / تحديث documents الثابتة ─────────────────────────────────────
    logger.info("📝 إنشاء documents الثابتة في rates...")
    from firebase_admin import firestore as fstore
    for currency, data in latest_by_curr.items():
        clean = {
            "currency":           currency,
            "buy_price":          data.get("buy_price", 0),
            "sell_price":         data.get("sell_price", 0),
            "change_percent":     data.get("change_percent", 0.0),
            "confidence_percent": data.get("confidence_percent", 0),
            "sources_count":      data.get("sources_count", 1),
            "timestamp":          data.get("timestamp") or fstore.SERVER_TIMESTAMP,
        }
        db.collection("rates").document(currency).set(clean)
        logger.info(f"   ✓ rates/{currency}: بيع={clean['sell_price']:,.0f} | شراء={clean['buy_price']:,.0f}")

    # ── ملخص نهائي ───────────────────────────────────────────────────────────
    logger.info("\n═══════════════════════════════════════════")
    logger.info("   ✅ اكتمل الترحيل بنجاح!              ")
    logger.info(f"   rates/        → {len(latest_by_curr)} documents ثابتة")
    logger.info(f"   rates_history → {len(all_history)} سجل تاريخي")
    logger.info("═══════════════════════════════════════════")


if __name__ == "__main__":
    migrate()
