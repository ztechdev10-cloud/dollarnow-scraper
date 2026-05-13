"""إعدادات السكرابر - تُقرأ من متغيرات البيئة"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram API
TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]
TELEGRAM_PHONE = os.environ["TELEGRAM_PHONE"]

# Firebase
FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json"
)
FIREBASE_PROJECT_ID = os.environ["FIREBASE_PROJECT_ID"]

# قنوات تلغرام المستهدفة مع درجة موثوقيتها الابتدائية (0-1)
TELEGRAM_CHANNELS = [
    {"username": "lira_today",            "reliability": 0.9},
    {"username": "sp_today_official",     "reliability": 0.95},
    {"username": "damascus_exchange",     "reliability": 0.85},
    {"username": "syria_dollar",          "reliability": 0.8},
    {"username": "sy_currency",           "reliability": 0.75},
    {"username": "lira_news",             "reliability": 0.7},
    # قنوات مضافة
    {"username": "dollars_com",           "reliability": 0.85},  # دولارز
    {"username": "syriastockss",          "reliability": 0.8},   # الأسهم السورية
]

# المواقع المستهدفة
WEB_SOURCES = [
    {
        "name": "sp_today",
        "url": "https://sp-today.com/currency/us_dollar",
        "reliability": 0.95,
    },
    {
        "name": "central_bank",
        "url": "https://lira.cb.gov.sy",
        "reliability": 0.7,
    },
    {
        "name": "lirat_org",
        "url": "https://lirat.org",
        "reliability": 0.92,
    },
    {
        "name": "dollar_syria",
        "url": "https://dollar-syria.com",
        "reliability": 0.88,
    },
    {
        "name": "sarafa_sy",
        "url": "https://xn--mgbah1a3hjkrd.com",
        "reliability": 0.85,
    },
]

# إعدادات الجدولة
WEB_SCRAPE_INTERVAL_MINUTES = 15
TELEGRAM_SESSION_FILE = "sessions/telegram_session"

# Firestore collection
RATES_COLLECTION = "rates"
SOURCES_COLLECTION = "sources"

# نافذة التجميع (بالدقائق)
AGGREGATION_WINDOW_MINUTES = 30

# حد أدنى/أقصى لسعر الدولار (للتحقق من صحة البيانات)
MIN_DOLLAR_RATE = 5_000
MAX_DOLLAR_RATE = 500_000

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = os.environ.get("LOG_FILE", "logs/scraper.log")
