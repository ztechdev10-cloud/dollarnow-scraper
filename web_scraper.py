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
    """جرّب عدة قنوات تلغرام عبر الويب"""
    channels = [
        "sp_today_official",
        "lira_today",
        "syria_dollar",
        "sy_currency",
        "damascus_exchange",
        "dollars_com",
        "syriastockss",
        "lira_news",
    ]
    import asyncio
    tasks = [scrape_telegram_channel(ch) for ch in channels]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for ch, r in zip(channels, results):
        if isinstance(r, tuple) and r[0] and r[1]:
            return r
    return None


async def scrape_sp_today() -> Optional[tuple[float, float]]:
    """اسحب سعر الدولار من sp-today.com (شراء، بيع)"""
    url = "https://sp-today.com/currency/us_dollar"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=HEADERS) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # محاولة 1: جدول
        table = soup.find("table", class_=lambda c: c and "price" in c.lower())
        if table:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    b, s = extract_prices(" ".join(c.get_text(strip=True) for c in cells))
                    if b and s:
                        logger.info(f"sp-today: buy={b}, sell={s}")
                        return b, s

        # محاولة 2: كل النص
        b, s = extract_prices(soup.get_text())
        if b and s:
            logger.info(f"sp-today (full-text): buy={b}, sell={s}")
            return b, s

        logger.warning("sp-today: لم يُعثر على سعر")
        return None

    except Exception as e:
        logger.error(f"sp-today error: {e}")
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
    """اسحب USD فقط من المواقع المحلية"""
    scrapers = {
        "telegram_web": scrape_telegram_channels_web,   # ← المصدر الجديد الأهم
        "sp_today":     scrape_sp_today,
        "central_bank": scrape_central_bank,
        "lirat_org":    scrape_lirat_org_usd,
        "dollar_syria": scrape_dollar_syria,
        "sarafa_sy":    scrape_sarafa_sy,
        "facebook_1":   lambda: scrape_facebook_page(
            "https://m.facebook.com/share/18gXHBwtd2/", "فيسبوك"
        ),
    }
    source_config = {s["name"]: s for s in WEB_SOURCES}
    results: list[RawRate] = []

    for name, fn in scrapers.items():
        result = await fn()
        if result:
            buy, sell = result
            reliability = source_config.get(name, {}).get("reliability", 0.7)
            results.append(RawRate(
                source=f"web_{name}",
                buy=buy, sell=sell,
                timestamp=datetime.now(timezone.utc),
                reliability=reliability,
                raw_text=f"web:{name}",
            ))

    return results


async def scrape_all_currencies() -> dict[str, list[RawRate]]:
    """
    يجلب أسعار جميع العملات ويُرجع {currency_code: [RawRate]}.

    الاستراتيجية:
    1. اجلب USD/SYP من المصادر المحلية (sp-today, lirat.org, إلخ).
    2. اجلب أسعار الصرف الدولية من Frankfurter API.
    3. اجلب سعر الذهب من metals.live / goldprice.org.
    4. احسب بقية العملات بالضرب.
    """
    results: dict[str, list[RawRate]] = {
        c: [] for c in ["USD", "EUR", "TRY", "SAR", "JOD", "XAU"]
    }

    # ── خطوة 1: USD/SYP ──────────────────────────────────────────────────
    usd_rates = await scrape_all_websites()
    results["USD"].extend(usd_rates)

    # احسب متوسط بسيط من مصادر USD
    usd_buys  = [r.buy  for r in usd_rates if r.buy]
    usd_sells = [r.sell for r in usd_rates if r.sell]

    if not usd_sells:
        logger.warning("لا يوجد سعر USD — تخطّي حساب العملات الأخرى")
        return results

    avg_usd_buy  = sum(usd_buys)  / len(usd_buys)  if usd_buys  else sum(usd_sells) / len(usd_sells)
    avg_usd_sell = sum(usd_sells) / len(usd_sells)
    logger.info(f"متوسط USD/SYP: buy={avg_usd_buy:.0f}, sell={avg_usd_sell:.0f}")

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
