import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Channel, Chat
from telethon.errors import (FloodWaitError, UserBannedInChannelError,
                              ChannelPrivateError, ChatWriteForbiddenError,
                              SlowModeWaitError)

load_dotenv()
API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]

# ─── إعداد الجلسة من StringSession (أبسط وأكثر موثوقية) ───
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")
if SESSION_STRING:
    SESSION = StringSession(SESSION_STRING)
    print(f"SESSION: loaded StringSession ({len(SESSION_STRING)} chars)", flush=True)
else:
    SESSION = "sessions/telegram_session"
    print("SESSION: loading from file", flush=True)

# ─── الرسالة (نص مع رابط تحميل بدل الملف) ───
DOWNLOAD_LINK = os.environ.get("DOWNLOAD_LINK", "https://gofile.io/d/wO3PP1")

MESSAGE = f"""\U0001f50d من معي؟ - تطبيق كاشف الأرقام السورية

تطبيق مجاني يكشف اسم صاحب اي رقم هاتف سوري فوراً!

يعمل مع: سيرياتيل - MTN - نور

- بحث فوري بالرقم او الاسم
- قاعدة بيانات من ملايين السوريين
- مجاني 100%

\U0001f4e5 رابط التحميل: {DOWNLOAD_LINK}

شاركه مع اهلك واصدقائك
"""

SEARCH_TERMS = [
    # ===== دمشق وريفها =====
    "دمشق","ريف دمشق","بيع وشراء دمشق","اعلانات دمشق","وظائف دمشق","سوق دمشق",
    "جرمانا","داريا","دوما","عدرا","قدسيا","يبرود","النبك","الزبداني","مضايا",
    "صيدنايا","معلولا","سرغايا","بلودان","القطيفة","حرستا","زملكا","عين ترما",
    "المليحة","ببيلا","بيت سحم","يلدا","مسرابا","شبعا","جديدة عرطوز","قطنا",
    "الكسوة","الغزلانية","برزة","التل","رنكوس","جيرود","المعرة","ضمير",
    "دير عطية","القنيطرة","نبع الصخر","عسال الورد","بكفيا","الضمير",
    "دمشق شباب","دمشق تعارف","دمشق اخبار","دمشق عقارات",

    # ===== حلب وريفها =====
    "حلب","ريف حلب","بيع وشراء حلب","اعلانات حلب","وظائف حلب","سوق حلب",
    "اعزاز","الباب","منبج","جرابلس","عفرين","الاتارب","اندان","حريتان",
    "السفيرة","خان العسل","تل رفعت","مارع","دابق","الفردوس","الراعي",
    "تادف","كويرس","ابو الظهور","سراقب","بنش","معرة مصرين","تفتناز",
    "كفرتخاريم","بزاعة","الاخترين","دير حافر","خناصر","صوران",
    "حلب شباب","حلب تعارف","حلب اخبار","حلب عقارات","حلب شمال",

    # ===== حمص وريفها =====
    "حمص","ريف حمص","بيع وشراء حمص","اعلانات حمص","وظائف حمص","سوق حمص",
    "تدمر","القصير","الرستن","تلبيسة","المخرم","الحولة","الزعفرانة",
    "الراستن","عين الحصن","حمص القديمة","الوعر","الحمدية","المشارفة",
    "قارة","ضبعة","مضايا","الربلة","تلكلخ","العريضة","حمص تعارف",

    # ===== حماة وريفها =====
    "حماة","ريف حماة","بيع وشراء حماة","اعلانات حماة","وظائف حماة","سوق حماة",
    "السلمية","مصياف","سوران","محردة","الغاب","خطاب","مورك","كفرزيتا",
    "اللطامنة","قلعة المضيق","الحمراء","طيبة الامام","حماة تعارف",

    # ===== اللاذقية وريفها =====
    "اللاذقية","ريف اللاذقية","بيع وشراء اللاذقية","اعلانات اللاذقية",
    "جبلة","القرداحة","الحفة","صلنفة","كسب","بلوران","قرداحة","الشيخ بدر",
    "سلمى","الهفة","رأس البسيط","برج اسلام","اللاذقية شباب","اللاذقية تعارف",

    # ===== طرطوس وريفها =====
    "طرطوس","ريف طرطوس","بيع وشراء طرطوس","اعلانات طرطوس","وظائف طرطوس",
    "بانياس","صافيتا","الشيخ بدر","مشتى الحلو","دريكيش","القدموس",
    "عين الحياة","الحميدية","الخربة","وادي العيون","طرطوس تعارف",

    # ===== ادلب وريفها =====
    "ادلب","ريف ادلب","بيع وشراء ادلب","اعلانات ادلب","وظائف ادلب","سوق ادلب",
    "معرة النعمان","جسر الشغور","سرمين","حارم","بنش","سلقين","ارمناز",
    "كفرنبل","خان شيخون","تفتناز","الدانا","باب الهوى","اطمة","سرمدا",
    "كللي","قاح","خربة الجوز","جبل الزاوية","ادلب تعارف","ادلب اخبار",

    # ===== دير الزور وريفها =====
    "دير الزور","ريف دير الزور","بيع وشراء دير الزور","اعلانات دير الزور",
    "البوكمال","الميادين","ابو كمال","الاشارة","الصور","الحسيان",
    "السبخة","الطيانة","العشارة","الكشكية","البصيرة","ذيبان",
    "دير الزور تعارف","دير الزور اخبار","دير الزور شباب",

    # ===== الرقة وريفها =====
    "الرقة","ريف الرقة","بيع وشراء الرقة","اعلانات الرقة","وظائف الرقة",
    "تل ابيض","الطبقة","السور","الكرامة","معدان","الرصافة",
    "صلوك","عين عيسى","الرقة تعارف","الرقة اخبار","الرقة شباب",

    # ===== الحسكة وريفها =====
    "الحسكة","ريف الحسكة","بيع وشراء الحسكة","اعلانات الحسكة","وظائف الحسكة",
    "القامشلي","المالكية","عامودا","رأس العين","تل تمر","الشدادي",
    "قبر شمرا","الدرباسية","عين العرب","كوباني","الجزيرة السورية",
    "الحسكة تعارف","القامشلي تعارف","الحسكة اخبار",

    # ===== درعا وريفها =====
    "درعا","ريف درعا","بيع وشراء درعا","اعلانات درعا","وظائف درعا","سوق درعا",
    "بصرى الشام","ازرع","الصنمين","نوى","اليادودة","طفس","انخل",
    "الحراك","جاسم","خربة غزالة","الشيخ مسكين","درعا تعارف","درعا اخبار",

    # ===== السويداء وريفها =====
    "السويداء","ريف السويداء","بيع وشراء السويداء","اعلانات السويداء",
    "شهبا","صلخد","قنوات","ملح","شقا","عرمان","المزرعة","السويداء تعارف",

    # ===== القنيطرة =====
    "القنيطرة","ريف القنيطرة","بيع وشراء القنيطرة","الجولان",
    "فيق","مجدل شمس","القنيطرة تعارف",

    # ===== عام وجاليات =====
    "سوريا","السوريون","السوريين","الشعب السوري","بيع وشراء سوريا",
    "اعلانات سوريا","وظائف سوريا","تعارف سوريا","اخبار سوريا",
    "زواج سوريا","شباب سوريا","مبوبة سوريا","سوق سوريا","عقارات سوريا",
    "السوريون في الكويت","السوريون في تركيا","السوريون في الخليج",
    "السوريون في المانيا","السوريون في لبنان","السوريون في مصر",
    "السوريون في السعودية","السوريون في الاردن","السوريون في اوروبا",
    "جاليات سورية","سوريا الحرة","سوريا الجديدة",
]

JOIN_ONLY = os.environ.get("JOIN_ONLY", "false").lower() == "true"

sent_ids = set()

def is_group(chat):
    if isinstance(chat, Chat):
        return True
    if isinstance(chat, Channel) and getattr(chat, 'megagroup', False):
        return True
    return False

async def ensure_connected(client):
    """تأكد من الاتصال وأعد الاتصال إذا لزم."""
    if not client.is_connected():
        print("RECONNECT: reconnecting...", flush=True)
        await client.connect()
        await asyncio.sleep(3)
        print("RECONNECT: done", flush=True)

async def search_and_collect(client, term, found):
    try:
        await ensure_connected(client)
        result = await client(SearchRequest(q=term, limit=50))
        for chat in result.chats:
            if chat.id in found or not is_group(chat):
                continue
            if getattr(chat, 'restricted', False):
                continue
            members = getattr(chat, 'participants_count', 0) or 0
            if members >= 20:
                found[chat.id] = chat
                print(f"FOUND: {chat.title} ({members})", flush=True)
        await asyncio.sleep(1)
    except FloodWaitError as e:
        print(f"FLOOD_SEARCH: {e.seconds}s — skipping", flush=True)
        if e.seconds > 60:
            return  # skip this term, don't block for hours
        await asyncio.sleep(e.seconds + 2)
    except Exception as e:
        err = str(e)
        if "disconnected" in err.lower():
            print(f"DISCONNECT: {term[:20]}, reconnecting...", flush=True)
            try:
                await client.connect()
                await asyncio.sleep(5)
                result = await client(SearchRequest(q=term, limit=50))
                for chat in result.chats:
                    if chat.id in found or not is_group(chat):
                        continue
                    if getattr(chat, 'restricted', False):
                        continue
                    members = getattr(chat, 'participants_count', 0) or 0
                    if members >= 20:
                        found[chat.id] = chat
                        print(f"FOUND_RETRY: {chat.title} ({members})", flush=True)
                await asyncio.sleep(1)
            except Exception as e2:
                print(f"ERR_SEARCH_RETRY: {term[:20]} | {str(e2)[:60]}", flush=True)
        else:
            print(f"ERR_SEARCH: {term[:20]} | {err[:60]}", flush=True)

async def send_to(client, chat, name, members):
    if chat.id in sent_ids:
        return
    try:
        await ensure_connected(client)
        try:
            await client(JoinChannelRequest(chat))
            await asyncio.sleep(2)
        except Exception:
            pass
        if JOIN_ONLY:
            sent_ids.add(chat.id)
            print(f"JOINED: {name} ({members})", flush=True)
            await asyncio.sleep(1)
            return
        await client.send_message(chat, MESSAGE, parse_mode='md')
        sent_ids.add(chat.id)
        print(f"OK: {name} ({members})", flush=True)
        await asyncio.sleep(5)
    except SlowModeWaitError as e:
        sent_ids.add(chat.id)
        print(f"SLOWMODE: {name} (wait {e.seconds}s)", flush=True)
    except FloodWaitError as e:
        wait = min(e.seconds, 300)
        print(f"FLOOD: {e.seconds}s (waiting {wait}s) - {name}", flush=True)
        await asyncio.sleep(wait + 3)
        try:
            await ensure_connected(client)
            await client.send_message(chat, MESSAGE, parse_mode='md')
            sent_ids.add(chat.id)
            print(f"OK_RETRY: {name}", flush=True)
            await asyncio.sleep(5)
        except Exception as e2:
            sent_ids.add(chat.id)
            print(f"FAIL_RETRY: {name} | {str(e2)[:60]}", flush=True)
    except (UserBannedInChannelError, ChannelPrivateError, ChatWriteForbiddenError):
        sent_ids.add(chat.id)
        print(f"SKIP: {name}", flush=True)
    except Exception as e:
        err = str(e)
        if any(x in err for x in ["FORBIDDEN","BANNED","RESTRICTED","PRIVACY","seconds is required"]):
            sent_ids.add(chat.id)
            print(f"SKIP: {name}", flush=True)
        elif "disconnected" in err.lower():
            sent_ids.add(chat.id)
            print(f"SKIP_DISCONNECT: {name}", flush=True)
        else:
            sent_ids.add(chat.id)
            print(f"FAIL: {name} | {err[:60]}", flush=True)

async def main():
    client = TelegramClient(
        SESSION, API_ID, API_HASH,
        connection_retries=10,
        retry_delay=5,
        timeout=60,
        auto_reconnect=True,
    )

    async with client:
        if not await client.is_user_authorized():
            print("ERROR: not authorized - check TELEGRAM_SESSION_B64", flush=True)
            return

        me = await client.get_me()
        print(f"LOGIN: {me.first_name} ({me.phone})", flush=True)
        print(f"TOTAL_TERMS: {len(SEARCH_TERMS)}", flush=True)

        # ─── تحميل القروبات المحفوظة من runs سابقة ───
        found = {}
        GROUPS_FILE = "groups.json"
        if os.path.exists(GROUPS_FILE):
            try:
                saved = json.load(open(GROUPS_FILE, encoding='utf-8'))
                for g in saved:
                    # نضيف stub يحتوي على id وtitle فقط لإعادة البناء
                    class _G:
                        pass
                    obj = _G()
                    obj.id = g["id"]
                    obj.title = g["title"]
                    obj.participants_count = g.get("members", 0)
                    obj.restricted = False
                    obj.megagroup = True
                    found[obj.id] = obj
                print(f"LOADED: {len(found)} saved groups", flush=True)
            except Exception as e:
                print(f"LOAD_ERR: {e}", flush=True)

        total_ok = 0

        for i, term in enumerate(SEARCH_TERMS):
            print(f"SEARCH {i+1}/{len(SEARCH_TERMS)}: {term}", flush=True)
            try:
                await search_and_collect(client, term, found)
            except Exception as e:
                print(f"ERR_SEARCH_OUTER: {e}", flush=True)

            to_send = sorted(
                [c for c in found.values() if c.id not in sent_ids],
                key=lambda x: getattr(x, 'participants_count', 0), reverse=True
            )
            for chat in to_send:
                try:
                    await send_to(client, chat, chat.title, getattr(chat, 'participants_count', 0))
                    if chat.id in sent_ids:
                        total_ok += 1
                        print(f"PROGRESS: {total_ok} sent / {len(found)} found", flush=True)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except BaseException as e:
                    print(f"ERR_LOOP: {chat.title[:30]} | {type(e).__name__}: {e}", flush=True)

        # ─── حفظ القروبات المكتشفة للـ runs القادمة ───
        try:
            data = [{"id": c.id, "title": c.title, "members": getattr(c, 'participants_count', 0)}
                    for c in found.values()]
            json.dump(data, open(GROUPS_FILE, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f"SAVED: {len(data)} groups to {GROUPS_FILE}", flush=True)
        except Exception as e:
            print(f"SAVE_ERR: {e}", flush=True)

        print(f"DONE: {total_ok} sent / {len(found)} found", flush=True)

asyncio.run(main())
