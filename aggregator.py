"""
خوارزمية تجميع الأسعار وحساب السعر النهائي لكل عملة.

الخطوات:
1. جمع البيانات من آخر 30 دقيقة
2. استبعاد القيم الشاذة (IQR method)
3. حساب المتوسط المرجح حسب موثوقية المصدر
4. تحديث موثوقية المصادر تلقائياً (نظام تعلّم)
5. كتابة النتيجة في Firestore (مع حقل currency)
"""
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from firebase_client import FirebaseClient
from telegram_monitor import RawRate

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = ["USD", "EUR", "TRY", "SAR", "JOD", "XAU"]


@dataclass
class AggregatedRate:
    buy: float
    sell: float
    sources_count: int
    confidence_percent: int
    change_percent: float
    currency: str = "USD"


class Aggregator:
    def __init__(self, firebase: FirebaseClient):
        self._firebase = firebase
        # قائمة انتظار بيانات آخر 30 دقيقة — مُفهرسة بالعملة
        self._raw_rates: dict[str, list[RawRate]] = {c: [] for c in SUPPORTED_CURRENCIES}
        # موثوقية المصادر
        self._reliabilities: dict[str, float] = {}
        # آخر سعر مُجمَّع للمقارنة لكل عملة
        self._last_avg: dict[str, Optional[float]] = {c: None for c in SUPPORTED_CURRENCIES}

    def add_rate(self, rate: RawRate, currency: str = "USD"):
        """أضف سعراً جديداً للقائمة (يُخزَّن تحت العملة المحددة)"""
        if currency not in self._raw_rates:
            self._raw_rates[currency] = []
        self._raw_rates[currency].append(rate)
        self._cleanup_old_entries(currency)

    def _cleanup_old_entries(self, currency: str):
        """احذف البيانات الأقدم من 30 دقيقة"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        self._raw_rates[currency] = [
            r for r in self._raw_rates[currency] if r.timestamp >= cutoff
        ]

    def _remove_outliers_iqr(self, values: list[float]) -> list[float]:
        """احذف القيم الشاذة باستخدام نطاق IQR"""
        if len(values) < 4:
            return values
        sorted_vals = sorted(values)
        q1 = statistics.quantiles(sorted_vals, n=4)[0]
        q3 = statistics.quantiles(sorted_vals, n=4)[2]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        return [v for v in values if lower <= v <= upper]

    def _get_reliability(self, source: str, default: float) -> float:
        """احصل على موثوقية المصدر"""
        if source in self._reliabilities:
            return self._reliabilities[source]
        fb_rel = self._firebase.get_source_reliability(source)
        if fb_rel is not None:
            self._reliabilities[source] = fb_rel
            return fb_rel
        return default

    def _update_source_reliability(self, source: str, was_accurate: bool):
        """نظام تعلّم بسيط لتحديث موثوقية المصدر"""
        current = self._reliabilities.get(source, 0.7)
        if was_accurate:
            new_rel = min(0.99, current + 0.01)
        else:
            new_rel = max(0.1, current - 0.05)
        self._reliabilities[source] = new_rel
        self._firebase.update_source_reliability(source, new_rel)

    def compute_and_save(self, currency: str = "USD") -> Optional[AggregatedRate]:
        """احسب السعر النهائي لعملة محددة واحفظه في Firestore"""
        self._cleanup_old_entries(currency)
        raw = self._raw_rates.get(currency, [])

        if not raw:
            logger.warning(f"[{currency}] لا توجد بيانات كافية للتجميع")
            return None

        sell_prices = [r.sell for r in raw if r.sell is not None]
        buy_prices  = [r.buy  for r in raw if r.buy  is not None]

        if not sell_prices:
            return None

        clean_sell = self._remove_outliers_iqr(sell_prices)
        clean_buy  = self._remove_outliers_iqr(buy_prices) if buy_prices else []

        weights: dict[str, float] = {}
        for rate in raw:
            if rate.sell in clean_sell:
                w = self._get_reliability(rate.source, rate.reliability)
                weights[rate.source] = w

        weighted_sell = self._weighted_average(
            [(r.sell, weights.get(r.source, r.reliability))
             for r in raw if r.sell in clean_sell]
        )
        weighted_buy = self._weighted_average(
            [(r.buy, weights.get(r.source, r.reliability))
             for r in raw if r.buy in clean_buy]
        ) if clean_buy else weighted_sell * 0.998

        last = self._last_avg.get(currency)
        change_pct = 0.0
        if last and last > 0:
            change_pct = ((weighted_sell - last) / last) * 100

        confidence = min(100, int(len(clean_sell) / max(len(sell_prices), 1) * 100))

        for rate in raw:
            if rate.sell is not None:
                is_accurate = abs(rate.sell - weighted_sell) / weighted_sell < 0.02
                self._update_source_reliability(rate.source, is_accurate)

        self._firebase.write_rate(
            buy=round(weighted_buy),
            sell=round(weighted_sell),
            sources_count=len(set(r.source for r in raw)),
            confidence=confidence,
            change_percent=round(change_pct, 2),
            currency=currency,
        )

        self._last_avg[currency] = weighted_sell
        logger.info(
            f"[{currency}] Aggregated: sell={weighted_sell:.0f}, buy={weighted_buy:.0f}, "
            f"sources={len(raw)}, confidence={confidence}%"
        )

        return AggregatedRate(
            buy=round(weighted_buy),
            sell=round(weighted_sell),
            sources_count=len(raw),
            confidence_percent=confidence,
            change_percent=round(change_pct, 2),
            currency=currency,
        )

    def compute_and_save_all(self) -> list[AggregatedRate]:
        """احسب وحفظ أسعار جميع العملات"""
        results = []
        for currency in SUPPORTED_CURRENCIES:
            result = self.compute_and_save(currency)
            if result:
                results.append(result)
        return results

    @staticmethod
    def _weighted_average(pairs: list[tuple[float, float]]) -> float:
        """احسب المتوسط المرجح من قائمة (قيمة, وزن)"""
        total_weight = sum(w for _, w in pairs)
        if total_weight == 0:
            return statistics.mean(v for v, _ in pairs)
        return sum(v * w for v, w in pairs) / total_weight
