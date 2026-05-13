"""عميل Firebase Admin SDK للكتابة في Firestore"""
import logging
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

from config import FIREBASE_CREDENTIALS_PATH, RATES_COLLECTION, SOURCES_COLLECTION

logger = logging.getLogger(__name__)


class FirebaseClient:
    def __init__(self):
        self._db = None
        self._initialize()

    def _initialize(self):
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        self._db = firestore.client()
        logger.info("Firebase client initialized")

    def write_rate(self, buy: float, sell: float, sources_count: int,
                   confidence: int, change_percent: float,
                   currency: str = "USD") -> str:
        """
        يكتب السعر في مكانين:
        1. rates/{currency}   ← السعر الحالي (document ثابت الاسم)
        2. rates_history/{id} ← السجل التاريخي (document جديد)
        """
        data = {
            "currency":           currency,
            "buy_price":          buy,
            "sell_price":         sell,
            "timestamp":          firestore.SERVER_TIMESTAMP,
            "sources_count":      sources_count,
            "confidence_percent": confidence,
            "change_percent":     change_percent,
        }

        # 1️⃣ السعر الحالي — document بنفس اسم العملة (يُحدَّث دائماً)
        self._db.collection(RATES_COLLECTION).document(currency).set(data)

        # 2️⃣ السجل التاريخي — document جديد في rates_history
        self._db.collection("rates_history").add(data)

        logger.info(f"[{currency}] ✓ بيع={sell:,.0f} | شراء={buy:,.0f} | مصادر={sources_count}")
        return currency

    def get_latest_rate(self, currency: str = "USD") -> dict | None:
        """جلب آخر سعر مسجّل من document الثابت"""
        doc = self._db.collection(RATES_COLLECTION).document(currency).get()
        return doc.to_dict() if doc.exists else None

    def update_source_reliability(self, source_name: str, reliability: float):
        """تحديث موثوقية مصدر في مجموعة sources"""
        self._db.collection(SOURCES_COLLECTION).document(source_name).set(
            {
                "reliability": reliability,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def get_source_reliability(self, source_name: str) -> float | None:
        """قراءة موثوقية مصدر"""
        doc = self._db.collection(SOURCES_COLLECTION).document(source_name).get()
        return doc.to_dict().get("reliability") if doc.exists else None

    def cleanup_old_rates(self, days: int = 90):
        """حذف الأسعار الأقدم من N يوماً (للتشغيل الدوري)"""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        old_docs = (
            self._db.collection(RATES_COLLECTION)
            .where("timestamp", "<", cutoff)
            .stream()
        )
        batch = self._db.batch()
        count = 0
        for doc in old_docs:
            batch.delete(doc.reference)
            count += 1
            if count % 500 == 0:
                batch.commit()
                batch = self._db.batch()
        if count % 500 != 0:
            batch.commit()
        logger.info(f"Deleted {count} old rate documents")
