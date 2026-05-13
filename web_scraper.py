"""سكرابر المواقع لاستخراج أسعار الصرف المتعددة"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from models import RawRate, extract_prices

# WEB_SOURCES مضمّنة هنا مباشرة (تجنّباً لاستيراد config الذي يحتاج متغيرات Telegram)
WEB_SOURCES = [
    {"name": "telegram_web", "url": "https://t.me/s/sp_today_official",        "reliability": 0.95},
    {"name": "sp_today",     "url": "https://sp-today.com/currency/us_dollar", "reliability": 0.95},
    {"name": "central_bank", "url": "https://lira.cb.gov.sy",                  "reliability": 0.70},
    {"name": "lirat_org",    "url": "https://lirat.org",                       "reliability": 0.92},
    {"name": "dollar_syria", "url": "https://dollar-syria.com",                "reliability": 0.88},
    {"name": "sarafa_sy",    "url": "https://xn--mgbah1a3hjkrd.com",           "reliability": 0.85},
]

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.9",
}

# ── ثوابت الذهب ──────────────────────────────────────────────────────────────
TROY_OZ_TO_GRAM = 31.1035
KARAT_21_FACTOR  = 21 / 24   # نسبة نقاء عيار 21


# ══════════════════════════════════════════════════════════════════════════════
#  1. جلب سعر الدولار / الليرة السورية  (المصدر الأساسي)
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_telegram_channel(channel: str) -> Optional[tuple[float, float]]:
    """
    اسحب آخر سعر من قناة تلغرام عبر t.me/s/ (server-side rendered — يعمل بدون JavaScript)
    """
    url = f"https://t.me/s/{channel}"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"t.me/s/{channel}: {resp.status_code}")
                return None

        soup = BeautifulSoup(resp.text, "html.parser")
        # الرسائل مرتبة من الأقدم للأحدث — نقرأها عكسياً لنأخذ الأحدث
        messages = soup.find_all("div", class_="tgme_widget_message_text")
        for msg in reversed(messages):
            text = msg.get_text(separator=" ")
            b, s = extract_prices(text)
            if b and s:
                logger.info(f"t.me/s/{channel}: buy={b}, sell={s}")
                return b, s
    except Exception as e:
        logger.warning(f"t.me/s/{channel}: {e}")
    return None


async def scrape_telegram_channels_web() -> Optional[tuple[float, float]]:
    """جرّب عدة قنوات تلغرام عبر الويب — مرتبة حسب الموثوقية"""
    # قنوات حقيقية تنشر أسعار الليرة السورية
    channels = [
        "sp_today_official",    # السعر اليوم الرسمي
        "liratoday",            # ليرة اليوم
        "lira_today",           # بديل
        "syria_dollar",         # دولار سوريا
        "syrianpound",          # الليرة السورية
        "dollar_sy",            # دولار سوريا
        "sy_currency",          # عملات سوريا
        "syr_dollar",           # الدولار السوري
        "syrian_exchange",      # صرافة سورية
        "damascus_exchange",    # صرافة دمشق
        "dollars_com",          # دولار
        "syriastockss",         # أسعار سوريا
        "lira_news",            # أخبار الليرة
        "exchange_sy",          # الصرافة السورية
        "dollar_sy24",          # دولار 24
        "lira24sy",             # ليرة 24
        "syp_rate",             # سعر الليرة
        "syrian_lira",          # الليرة
        "dolar_syria",          # دولار سوريا
        "currency_sy",          # العملة السورية
    ]
    import asyncio
    # جرّب على دفعات لتسريع العملية
    batch_size = 5
    for i in range(0, len(channels), batch_size):
        batch = channels[i:i + batch_size]
        tasks = [scrape_telegram_channel(ch) for ch in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ch, r in zip(batch, results):
            if isinstance(r, tuple) and r[0] and r[1]:
                logger.info(f"✅ نجح المصدر: t.me/s/{ch}")
                return r
    return None


async def scrape_sp_today() -> Optional[tuple[float, float]]:
    """
    اسحب سعر الدولار من sp-today.com
    الصفحة SSR — تعمل بدون JavaScript من GitHub Actions
    """
    import re

    # ← الرابط الصحيح: us-dollar بـ hyphen لا us_dollar
    urls = [
        "https://sp-today.com/currency/us-dollar",          # English version — أسهل للـ parsing
        "https://sp-today.com/ar/currency/us-dollar",       # Arabic version
        "https://sp-today.com/currency/us_dollar",          # احتياطي (underscore قديم)
    ]

    HEADERS_SPTODAY = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        "Referer":         "https://sp-today.com/",
    }

    for url in urls:
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers=HEADERS_SPTODAY,
                follow_redirects=True
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"sp-today ({url}): {resp.status_code}")
                    continue

            text = resp.text
            soup = BeautifulSoup(text, "html.parser")
            page_text = soup.get_text(separator=" ")

            # محاولة 1: regex مباشر على النص الإنجليزي "Buy X Sell Y"
            m = re.search(
                r"Buy\s+([\d,]+)\s*SYP.*?Sell\s+([\d,]+)\s*SYP",
                page_text, re.IGNORECASE | re.DOTALL
            )
            if m:
                buy  = float(m.group(1).replace(",", ""))
                sell = float(m.group(2).replace(",", ""))
                if 5000 < buy < 1_000_000 and 5000 < sell < 1_000_000:
                    logger.info(f"sp-today ✅ buy={buy:.0f}, sell={sell:.0f} ({url})")
                    return min(buy, sell), max(buy, sell)

            # محاولة 2: regex "Sell X Buy Y"
            m = re.search(
                r"Sell\s+([\d,]+)\s*SYP.*?Buy\s+([\d,]+)\s*SYP",
                page_text, re.IGNORECASE | re.DOTALL
            )
            if m:
                sell = float(m.group(1).replace(",", ""))
                buy  = float(m.group(2).replace(",", ""))
                if 5000 < buy < 1_000_000 and 5000 < sell < 1_000_000:
                    logger.info(f"sp-today ✅ buy={buy:.0f}, sell={sell:.0f} (sell-first)")
                    return min(buy, sell), max(buy, sell)

            # محاولة 3: أول جدول تحويل (صف "1 USD = X SYP buy | Y SYP sell")
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                for row in rows:
                    cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                    row_text = " ".join(cells)
                    # ابحث عن صف يحتوي "1" و SYP
                    nums = re.findall(r"[\d,]{5,}", row_text)
                    if len(nums) >= 2:
                        v1 = float(nums[0].replace(",", ""))
                        v2 = float(nums[1].replace(",", ""))
                        if 5000 < v1 < 1_000_000 and 5000 < v2 < 1_000_000:
                            logger.info(f"sp-today (table) ✅ buy={min(v1,v2):.0f}, sell={max(v1,v2):.0f}")
                            return min(v1, v2), max(v1, v2)

            # محاولة 4: extract_prices العام
            b, s = extract_prices(page_text)
            if b and s:
                logger.info(f"sp-today (extract) ✅ buy={b:.0f}, sell={s:.0f}")
                return b, s

            logger.warning(f"sp-today: لم يُعثر على سعر في {url}")

        except Exception as e:
            logger.warning(f"sp-today ({url}): {e}")

    logger.error("sp-today: فشلت جميع المحاولات")
    return None


async def scrape_sp_today_api() -> Optional[tuple[float, float]]:
    """
    اسحب من sp-today API غير الرسمي — JSON مباشر بدون HTML parsing
    """
    import re, json as _json

    # بعض endpoints معروفة من sp-today
    api_urls = [
        "https://sp-today.com/api/currency/USD",
        "https://sp-today.com/api/rates",
        "https://sp-today.com/api/v1/rates",
        "https://sp-today.com/api/v1/currency/USD",
        "https://sp-today.com/widget-data?currency=USD",
    ]

    for url in api_urls:
        try:
            async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                try:
                    data = resp.json()
                    text = str(data)
                except Exception:
                    text = resp.text

                b, s = extract_prices(text)
                if b and s:
                    logger.info(f"sp-today API ✅ buy={b:.0f}, sell={s:.0f} ({url})")
                    return b, s

                # ابحث عن buy/sell مباشرة في JSON
                for key_buy in ["buy", "purchase", "buying", "bid"]:
                    for key_sell in ["sell", "sale", "selling", "ask"]:
                        if isinstance(data, dict):
                            buy_val  = data.get(key_buy) or data.get(key_buy.upper())
                            sell_val = data.get(key_sell) or data.get(key_sell.upper())
                            if buy_val and sell_val:
                                try:
                                    b2 = float(str(buy_val).replace(",", ""))
                                    s2 = float(str(sell_val).replace(",", ""))
                                    if 5000 < b2 < 1_000_000:
                                        logger.info(f"sp-today API JSON ✅ buy={b2:.0f}, sell={s2:.0f}")
                                        return min(b2, s2), max(b2, s2)
                                except Exception:
                                    pass
        except Exception as e:
            logger.debug(f"sp-today API ({url}): {e}")

    return None


async def scrape_central_bank() -> Optional[tuple[float, float]]:
    """اسحب السعر الرسمي من البنك المركزي السوري"""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=HEADERS) as client:
            resp = await client.get("https://lira.cb.gov.sy", follow_redirects=True)
            resp.raise_for_status()
        b, s = extract_prices(BeautifulSoup(resp.text, "html.parser").get_text())
        if b and s:
            logger.info(f"Central bank: buy={b}, sell={s}")
            return b, s
    except Exception as e:
        logger.error(f"Central bank error: {e}")
    return None


async def scrape_lirat_org_usd() -> Optional[tuple[float, float]]:
    """اسحب سعر الدولار من lirat.org"""
    urls_to_try = [
        "https://lirat.org",
        "https://lirat.org/usd",
        "https://lirat.org/dollar",
        "https://lirat.org/api/rates",
        "https://lirat.org/api/v1/rates",
    ]
    for url in urls_to_try:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=HEADERS) as client:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code != 200:
                    continue

            # حاول JSON أولاً
            try:
                data = resp.json()
                text = str(data)
            except Exception:
                text = resp.text

            # ابحث في __NEXT_DATA__ (Next.js)
            import re, json as _json
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', text, re.DOTALL)
            if m:
                try:
                    nd = _json.loads(m.group(1))
                    text = str(nd)
                except Exception:
                    pass

            b, s = extract_prices(text)
            if b and s:
                logger.info(f"lirat.org ({url}): buy={b}, sell={s}")
                return b, s
        except Exception as e:
            logger.warning(f"lirat.org ({url}): {e}")
    return None


async def scrape_dollar_syria() -> Optional[tuple[float, float]]:
    """اسحب سعر الدولار من dollar-syria.com"""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get("https://dollar-syria.com")
            resp.raise_for_status()
        b, s = extract_prices(BeautifulSoup(resp.text, "html.parser").get_text(separator=" "))
        if b and s:
            logger.info(f"dollar-syria.com: buy={b}, sell={s}")
            return b, s
        logger.warning("dollar-syria.com: لم يُعثر على سعر")
    except Exception as e:
        logger.error(f"dollar-syria.com error: {e}")
    return None


async def scrape_wisesheets_or_fawaz_syp() -> Optional[tuple[float, float]]:
    """
    جلب سعر تقريبي للدولار مقابل الليرة السورية من مصادر API مفتوحة.
    ملاحظة: هذه المصادر قد تعطي السعر الرسمي — نضرب في معامل السوق الموازي.
    """
    # معامل السوق الموازي التقريبي (السعر الفعلي ÷ السعر الرسمي)
    # CBK rate ≈ 2,512 | سعر السوق ≈ 13,000+ → معامل ≈ 5-6
    # هذه قيمة تقريبية فقط — المصادر الأساسية هي تلغرام والمواقع المحلية
    BLACK_MARKET_FACTOR = 1.0  # لا نستخدم هذا المصدر إلا كآخر حل

    urls = [
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
        "https://latest.currency-api.pages.dev/v1/currencies/usd.json",
    ]
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                data = resp.json().get("usd", {})
                syp_rate = data.get("syp")
                if syp_rate and float(syp_rate) > 1000:
                    rate = float(syp_rate) * BLACK_MARKET_FACTOR
                    spread = rate * 0.01
                    buy  = round(rate - spread)
                    sell = round(rate + spread)
                    logger.info(f"fawaz API: USD/SYP = {rate:.0f}")
                    return buy, sell
        except Exception as e:
            logger.warning(f"fawaz API: {e}")
    return None


async def scrape_sarafa_sy() -> Optional[tuple[float, float]]:
    """اسحب سعر الدولار من صرافة سوريا"""
    import re, json as _json
    urls = [
        "https://xn--mgbah1a3hjkrd.com",
        "https://xn--mgbah1a3hjkrd.com/api/rates",
        "https://xn--mgbah1a3hjkrd.com/api/v1/dollar",
    ]
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue

            try:
                text = str(resp.json())
            except Exception:
                text = resp.text

            # ابحث في __NEXT_DATA__
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', text, re.DOTALL)
            if m:
                try:
                    text = str(_json.loads(m.group(1)))
                except Exception:
                    pass

            b, s = extract_prices(text)
            if b and s:
                logger.info(f"sarafa.sy ({url}): buy={b}, sell={s}")
                return b, s
        except Exception as e:
            logger.warning(f"sarafa.sy ({url}): {e}")
    return None


async def scrape_facebook_page(page_url: str, page_name: str) -> Optional[tuple[float, float]]:
    """اسحب سعر الدولار من صفحة فيسبوك عامة"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "ar,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=headers, follow_redirects=True) as client:
            resp = await client.get(page_url)
            resp.raise_for_status()
        b, s = extract_prices(BeautifulSoup(resp.text, "html.parser").get_text(separator=" "))
        if b and s:
            logger.info(f"Facebook {page_name}: buy={b}, sell={s}")
            return b, s
    except Exception as e:
        logger.warning(f"Facebook {page_name}: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  2. أسعار الصرف العالمية (Frankfurter API — مجاني بلا مفتاح)
# ══════════════════════════════════════════════════════════════════════════════

async def get_forex_rates_vs_usd() -> dict[str, float]:
    """
    جلب أسعار EUR, TRY, SAR, JOD مقابل الدولار.
    يُرجع: {"EUR": 0.92, "TRY": 38.0, "SAR": 3.75, "JOD": 0.709}
    حيث القيمة = كم وحدة من العملة تساوي 1 دولار.

    المصادر (بالترتيب):
    1. Frankfurter (EUR, TRY فقط — ECB currencies)
    2. @fawazahmed0 على jsDelivr (شامل لجميع العملات)
    3. قيم ثابتة احتياطية (SAR, JOD مربوطة بالدولار)
    """
    NEEDED = {"EUR", "TRY", "SAR", "JOD"}
    # قيم ثابتة احتياطية (SAR مربوطة 3.75، JOD مربوطة 0.709)
    FALLBACK = {"EUR": 0.92, "TRY": 38.0, "SAR": 3.75, "JOD": 0.709}

    result: dict[str, float] = {}

    # ── محاولة 1: Frankfurter (EUR, TRY) ─────────────────────────────────
    for url in [
        "https://api.frankfurter.dev/v1/latest?from=USD&to=EUR,TRY",
        "https://api.frankfurter.app/latest?from=USD&to=EUR,TRY",
    ]:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                rates = data.get("rates", {})
                result.update({k: v for k, v in rates.items() if k in NEEDED})
                if result:
                    logger.info(f"Frankfurter: {result}")
                    break
        except Exception as e:
            logger.warning(f"Frankfurter: {e}")

    # ── محاولة 2: @fawazahmed0 / jsDelivr (شامل لجميع العملات) ──────────
    missing = NEEDED - set(result.keys())
    if missing:
        for url in [
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            "https://latest.currency-api.pages.dev/v1/currencies/usd.json",
        ]:
            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json().get("usd", {})
                    # المفاتيح بالحروف الصغيرة: "eur", "try", "sar", "jod"
                    for code in missing:
                        v = data.get(code.lower())
                        if v:
                            result[code] = float(v)
                    logger.info(f"jsDelivr rates: {result}")
                    break
            except Exception as e:
                logger.warning(f"jsDelivr: {e}")

    # ── احتياطي نهائي لأي عملة ما زالت ناقصة ────────────────────────────
    for code in NEEDED:
        if code not in result:
            result[code] = FALLBACK[code]
            logger.warning(f"استخدام قيمة احتياطية: 1 USD = {FALLBACK[code]} {code}")

    logger.info(f"أسعار الصرف النهائية: {result}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  3. سعر الذهب العالمي
# ══════════════════════════════════════════════════════════════════════════════

async def get_gold_price_usd_per_oz() -> Optional[float]:
    """
    جلب سعر الذهب بالدولار للأوقية (troy oz) من metals.live.
    يُرجع السعر بالدولار أو None عند الفشل.
    """
    # محاولة 1: metals.live (مع تجاهل أخطاء SSL)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=False) as client:
            resp = await client.get("https://api.metals.live/v1/spot/gold")
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                price = float(data[0].get("gold", 0))
            elif isinstance(data, dict):
                price = float(data.get("gold", 0))
            else:
                price = 0.0
            if price > 1000:
                logger.info(f"Gold price (metals.live): ${price}/oz")
                return price
    except Exception as e:
        logger.warning(f"metals.live error: {e}")

    # محاولة 2: goldprice.org (scraping)
    try:
        headers_gold = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": "https://goldprice.org/",
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=headers_gold) as client:
            resp = await client.get("https://data-asg.goldprice.org/dbXRates/USD")
            resp.raise_for_status()
            data = resp.json()
            # يُرجع {"items": [{"xauPrice": 2350.5, ...}]}
            items = data.get("items", [])
            if items:
                price = float(items[0].get("xauPrice", 0))
                if price > 1000:
                    logger.info(f"Gold price (goldprice.org): ${price}/oz")
                    return price
    except Exception as e:
        logger.warning(f"goldprice.org error: {e}")

    logger.error("تعذّر جلب سعر الذهب من جميع المصادر")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  4. حساب أسعار الليرة السورية لكل العملات
# ══════════════════════════════════════════════════════════════════════════════

def calculate_syp_rates(
    usd_buy: float,
    usd_sell: float,
    forex_vs_usd: dict[str, float],
    gold_usd_per_oz: Optional[float]
) -> dict[str, tuple[float, float]]:
    """
    يحسب (شراء، بيع) بالليرة السورية لكل عملة.

    المنطق:
    - forex_vs_usd[EUR] = كم EUR = 1 USD  → مثلاً 0.92
    - إذن 1 EUR = (1/0.92) USD = 1.087 USD
    - EUR/SYP_sell = 1.087 × USD_sell
    """
    rates: dict[str, tuple[float, float]] = {}

    # USD (أساس)
    rates["USD"] = (usd_buy, usd_sell)

    # العملات الأجنبية الأخرى
    for code in ["EUR", "TRY", "SAR", "JOD"]:
        rate_vs_usd = forex_vs_usd.get(code)
        if rate_vs_usd and rate_vs_usd > 0:
            # كم وحدة من العملة تساوي 1 دولار ← inverit للحصول على قيمة 1 وحدة بالدولار
            one_unit_in_usd = 1.0 / rate_vs_usd
            sell = round(usd_sell * one_unit_in_usd)
            buy  = round(usd_buy  * one_unit_in_usd)
            rates[code] = (buy, sell)
            logger.info(f"{code}/SYP: buy={buy}, sell={sell}  (1 {code} = {one_unit_in_usd:.4f} USD)")

    # الذهب عيار 21 (سعر الغرام)
    if gold_usd_per_oz and gold_usd_per_oz > 0:
        gold_per_gram_usd  = gold_usd_per_oz / TROY_OZ_TO_GRAM
        gold_21k_per_gram  = gold_per_gram_usd * KARAT_21_FACTOR
        gold_sell = round(gold_21k_per_gram * usd_sell)
        gold_buy  = round(gold_21k_per_gram * usd_buy)
        rates["XAU"] = (gold_buy, gold_sell)
        logger.info(f"Gold 21k/gram: buy={gold_buy}, sell={gold_sell} SYP  (${gold_21k_per_gram:.2f}/g)")

    return rates


# ══════════════════════════════════════════════════════════════════════════════
#  5. الدوال الرئيسية المُصدَّرة
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_all_websites() -> list[RawRate]:
    """
    اسحب USD/SYP من المواقع المحلية فقط.
    ملاحظة: لا نستخدم البنك المركزي ولا fawaz API لأنهما يعطيان السعر الرسمي
    لا سعر السوق الموازي.
    """
    scrapers = {
        "telegram_web":  scrape_telegram_channels_web,  # ← الأولوية القصوى
        "sp_today":      scrape_sp_today,               # ← موثوق جداً (URL مصحح)
        "sp_today_api":  scrape_sp_today_api,           # ← API sp-today احتياطي
        "lirat_org":     scrape_lirat_org_usd,          # ← موثوق
        "dollar_syria":  scrape_dollar_syria,           # ← جيد
        "sarafa_sy":     scrape_sarafa_sy,              # ← احتياطي
        "facebook_1":    lambda: scrape_facebook_page(
            "https://m.facebook.com/share/18gXHBwtd2/", "فيسبوك"
        ),
        # ❌ central_bank  — سعر رسمي ≠ سعر السوق
        # ❌ fawaz_api     — API عالمي ≠ سعر السوق السوري
    }
    # موثوقية كل مصدر — كلما كان أعلى كان وزنه في الوسيط أكبر
    RELIABILITY = {
        "telegram_web": 0.95,
        "sp_today":     0.93,
        "sp_today_api": 0.90,
        "lirat_org":    0.88,
        "dollar_syria": 0.85,
        "sarafa_sy":    0.80,
        "facebook_1":   0.75,
    }

    results: list[RawRate] = []
    for name, fn in scrapers.items():
        try:
            result = await fn()
            if result:
                buy, sell = result
                results.append(RawRate(
                    source=f"web_{name}",
                    buy=buy, sell=sell,
                    timestamp=datetime.now(timezone.utc),
                    reliability=RELIABILITY.get(name, 0.7),
                    raw_text=f"web:{name}",
                ))
        except Exception as e:
            logger.warning(f"خطأ في {name}: {e}")

    return results


def _weighted_median(rates: list[RawRate], key: str) -> float:
    """
    وسيط موزون حسب الموثوقية — يرفض الأسعار الشاذة تلقائياً.
    key: 'buy' أو 'sell'
    """
    values = [(getattr(r, key), r.reliability) for r in rates if getattr(r, key)]
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0][0]

    # 1. احسب الوسيط البسيط لكشف الشاذ
    prices = sorted(v[0] for v in values)
    median = prices[len(prices) // 2]

    # 2. ارفض الأسعار التي تبعد أكثر من 15% عن الوسيط
    filtered = [(p, w) for p, w in values if abs(p - median) / median <= 0.15]
    if not filtered:
        filtered = values  # إذا الكل شاذ، خذ الكل

    # 3. متوسط موزون بالموثوقية
    total_weight = sum(w for _, w in filtered)
    result = sum(p * w for p, w in filtered) / total_weight

    logger.info(
        f"  مصادر مقبولة: {len(filtered)}/{len(values)} | "
        f"نتيجة: {result:.0f} | "
        f"مرفوضة: {[round(p) for p,_ in values if abs(p-median)/median > 0.15]}"
    )
    return result


async def scrape_all_currencies() -> dict[str, list[RawRate]]:
    """
    يجلب أسعار جميع العملات ويُرجع {currency_code: [RawRate]}.

    الاستراتيجية:
    1. اجلب USD/SYP من المصادر المحلية (sp-today, lirat.org, إلخ).
    2. اجلب أسعار الصرف الدولية من Frankfurter API.
    3. اجلب سعر الذهب من metals.live / goldprice.org.
    4. احسب بقية العملات بالضرب مع فلترة الشاذ.
    """
    results: dict[str, list[RawRate]] = {
        c: [] for c in ["USD", "EUR", "TRY", "SAR", "JOD", "XAU"]
    }

    # ── خطوة 1: USD/SYP ──────────────────────────────────────────────────
    usd_rates = await scrape_all_websites()
    results["USD"].extend(usd_rates)

    # لوغ كل مصدر ناجح
    for r in usd_rates:
        logger.info(f"  [{r.source}] بيع={round(r.sell):,} | شراء={round(r.buy):,} | موثوقية={r.reliability}")

    usd_sells = [r for r in usd_rates if r.sell]
    usd_buys  = [r for r in usd_rates if r.buy]

    if not usd_sells:
        logger.warning("لا يوجد سعر USD — تخطّي حساب العملات الأخرى")
        return results

    # استخدم الوسيط الموزون بدلاً من المتوسط لرفض الأسعار الشاذة
    avg_usd_sell = _weighted_median(usd_sells, "sell")
    avg_usd_buy  = _weighted_median(usd_buys,  "buy") if usd_buys else avg_usd_sell * 0.995
    logger.info(f"✅ USD/SYP النهائي: بيع={avg_usd_sell:.0f} | شراء={avg_usd_buy:.0f}")

    # ── خطوة 2+3: أسعار الصرف الدولية + الذهب ───────────────────────────
    import asyncio
    forex_rates, gold_price = await asyncio.gather(
        get_forex_rates_vs_usd(),
        get_gold_price_usd_per_oz(),
    )

    # ── خطوة 4: احسب الأسعار لكل عملة ──────────────────────────────────
    syp_rates = calculate_syp_rates(avg_usd_buy, avg_usd_sell, forex_rates, gold_price)

    now = datetime.now(timezone.utc)
    for code, (buy, sell) in syp_rates.items():
        if code == "USD":
            continue  # USD مضافة بالفعل
        results[code].append(RawRate(
            source=f"calculated_from_usd",
            buy=buy, sell=sell,
            timestamp=now,
            reliability=0.88,
            raw_text=f"cross_rate:{code}",
        ))

    # لوغ ملخص
    for code, rates_list in results.items():
        if rates_list:
            r = rates_list[-1]
            logger.info(f"  {code}: buy={r.buy}, sell={r.sell}")

    return results
