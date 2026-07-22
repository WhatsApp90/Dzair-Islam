import os
import json
import logging
import random
import requests
from urllib.parse import quote
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ── التوكن ──────────────────────────────────────────────────────────────────
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── ملف الحفظ الدائم ─────────────────────────────────────────────────────────
DB_FILE = "data.json"

def load_db() -> dict:
    """تحميل البيانات من الملف عند بدء التشغيل."""
    default = {
        "alarms":      {},
        "auto":        [],
        "quiz":        [],
        "quiz_scores": {},
        "surah_cache": {},
    }
    if not os.path.exists(DB_FILE):
        return default
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # تحويل المفاتيح الرقمية من string إلى int
        data["alarms"]      = {int(k): v for k, v in data.get("alarms", {}).items()}
        data["quiz_scores"] = {int(k): v for k, v in data.get("quiz_scores", {}).items()}
        data["auto"]        = data.get("auto", [])
        data["quiz"]        = data.get("quiz", [])
        data["surah_cache"] = data.get("surah_cache", {})
        return data
    except Exception as e:
        logger.error(f"خطأ في تحميل البيانات: {e}")
        return default

def save_db():
    """حفظ البيانات في الملف (بدون surah_cache لأنها مؤقتة)."""
    try:
        data = {
            "alarms":      db["alarms"],
            "auto":        list(db["auto"]),
            "quiz":        list(db["quiz"]),
            "quiz_scores": db["quiz_scores"],
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ البيانات: {e}")

# ── تحميل البيانات وتحويل القوائم إلى sets ───────────────────────────────────
_raw = load_db()
db = {
    "alarms":      _raw["alarms"],
    "auto":        set(_raw["auto"]),
    "quiz":        set(_raw["quiz"]),
    "quiz_scores": _raw["quiz_scores"],
    "surah_cache": {},       # {reciter_key: [{sura_id, name, rec_id}]} — مؤقتة فقط
}

# ══════════════════════════════════════════════════════════════════
#  أسماء السور الـ 114
# ══════════════════════════════════════════════════════════════════
SURAH_NAMES = [
    "الفاتحة", "البقرة", "آل عمران", "النساء", "المائدة",
    "الأنعام", "الأعراف", "الأنفال", "التوبة", "يونس",
    "هود", "يوسف", "الرعد", "إبراهيم", "الحجر",
    "النحل", "الإسراء", "الكهف", "مريم", "طه",
    "الأنبياء", "الحج", "المؤمنون", "النور", "الفرقان",
    "الشعراء", "النمل", "القصص", "العنكبوت", "الروم",
    "لقمان", "السجدة", "الأحزاب", "سبأ", "فاطر",
    "يس", "الصافات", "ص", "الزمر", "غافر",
    "فصلت", "الشورى", "الزخرف", "الدخان", "الجاثية",
    "الأحقاف", "محمد", "الفتح", "الحجرات", "ق",
    "الذاريات", "الطور", "النجم", "القمر", "الرحمن",
    "الواقعة", "الحديد", "المجادلة", "الحشر", "الممتحنة",
    "الصف", "الجمعة", "المنافقون", "التغابن", "الطلاق",
    "التحريم", "الملك", "القلم", "الحاقة", "المعارج",
    "نوح", "الجن", "المزمل", "المدثر", "القيامة",
    "الإنسان", "المرسلات", "النبأ", "النازعات", "عبس",
    "التكوير", "الانفطار", "المطففين", "الانشقاق", "البروج",
    "الطارق", "الأعلى", "الغاشية", "الفجر", "البلد",
    "الشمس", "الليل", "الضحى", "الشرح", "التين",
    "العلق", "القدر", "البينة", "الزلزلة", "العاديات",
    "القارعة", "التكاثر", "العصر", "الهمزة", "الفيل",
    "قريش", "الماعون", "الكوثر", "الكافرون", "النصر",
    "المسد", "الإخلاص", "الفلق", "الناس",
]

# ══════════════════════════════════════════════════════════════════
#  قائمة القراء الجزائريين
#  source:
#    "mp3quran"  → server/{num:03d}.mp3
#    "way2quran" → media.way2quran.com/audios/{slug}/{num:03d}.mp3
#    "assabile"  → AJAX لجلب IDs + CDN
# ══════════════════════════════════════════════════════════════════
# ── ملفات سعيد دباح على archive.org (اسم الملف الحقيقي لكل سورة) ────────────
DABBAH_ARCHIVE_ID = "20240321_20240321_1640"
DABBAH_FILES = {
    1:  "001  1  القارئ سعيد دباح الجزائري - سورة الفاتحة  - جودة عالية.mp3",
    2:  "002  2  سورة البقرة كاملة بصوت سعيد دباح الجزائري.mp3",
    3:  "003  3  القارئ سعيد دباح - تلاوة من سورة ال عمران - تراويح رمضان 2018.mp3",
    4:  "004  4  سعيد دباح - تلاوة من سورة النساء - تراويح 2018 بجودة عالية.mp3",
    5:  "005  5  القارئ سعيد دباح ماتيسر من سورة المائد ة.mp3",
    6:  "006  6  القارئ سعيد دباح ماتيسر من سورة الانعام  said debbah.mp3",
    7:  "007  7  القارئ سعيد دباح  تلاوة من سورة الأعراف - تراويح رمضان جودة عالية 2018.mp3",
    8:  "008  8  القارئ سعيد دباح  تلاوة من سورة الأنفال - تراويح رمضان 2018 - جودة عالية.mp3",
    9:  "009  9  القارئ سعيد دباح  سورة التوبة - ( تسجيلات جديدة - جودة عالية ) حصريا على قناتنا 2018.mp3",
    10: "010  10  القارئ سعيد دباح  تلاوة من سورة يونس - جودة عالية.mp3",
    11: "011  11  سورة هود بجودة عالية للقارئ الجزائري سعيد دباح.mp3",
    12: "012  12  سعيد دباح  سورة يوسف.mp3",
    13: "013  13  القارئ سعيد دباح سورة الرعد كاملة تلآوة رائعة.mp3",
    16: "016    16  تلاوة خاشعة للقارئ سعيد دباح من سورة النحل.mp3",
    18: "018   18  القارئ سعيد دباح سورة الكهف كاملة.mp3",
    19: "019   19  سعيد دباح  سورة مريم كاملة   اشترك بالقناة.mp3",
    20: "020    20  القارئ سعيد دباح  تلاوة من سورة طه - جودة عالية.mp3",
    21: "021   21  من أروع مارتل سعيد دباح الجزائري من سورة الانبياء.mp3",
    22: "022   22  القارئ سعيد دباح  سورة الحج - جودة عالية 2018.mp3",
}

ALGERIAN_RECITERS = [
    {
        "key": "dabbah",
        "name": "الشيخ سعيد دباح الجزائري",
        "riwaya": "حفص عن عاصم",
        "source": "archive",
        # السور المتاحة: الأرقام مأخوذة من DABBAH_FILES
        "surahs": sorted(DABBAH_FILES.keys()),
    },
    {
        "key": "yaseen",
        "name": "الشيخ ياسين الجزائري",
        "riwaya": "ورش عن نافع",
        "source": "mp3quran",
        "server": "https://server11.mp3quran.net/qari",
        "surahs": list(range(1, 115)),
    },
    {
        "key": "riad",
        "name": "الشيخ رياض الجزائري",
        "riwaya": "حفص عن عاصم + مجوّد",
        "source": "assabile",
        "slug": "riad-al-djazairi",
        "person_id": 488,
        "collection_id": 531,    # حفص مرتل
    },
    {
        "key": "rachid",
        "name": "الشيخ رشيد بلعالية",
        "riwaya": "ورش عن نافع",
        "source": "assabile",
        "slug": "rachid-belalia",
        "person_id": 219,
        "collection_id": 0,
    },
    {
        "key": "zakaria",
        "name": "الشيخ زكريا حمامة",
        "riwaya": "ورش عن نافع",
        "source": "assabile",
        "slug": "zakaria-hamama",
        "person_id": 222,
        "collection_id": 0,
    },
    {
        "key": "mansour",
        "name": "الشيخ منصور الوهراني الجزائري",
        "riwaya": "ورش عن نافع",
        "source": "assabile",
        "slug": "mansour-el-wahrani-aljazaery",
        "person_id": 504,
        "collection_id": 0,
    },
    {
        "key": "hamza",
        "name": "الشيخ حمزة الجزائري",
        "riwaya": "حفص عن عاصم",
        "source": "way2quran",
        "slug": "hamza-al-jazairi",
        "surahs": list(range(1, 115)),
    },
    {
        "key": "youssef",
        "name": "الشيخ يوسف الجزائري",
        "riwaya": "ورش عن نافع",
        "source": "way2quran",
        "slug": "youssouf-al-jazairi",
        "surahs": list(range(1, 115)),
    },
]

# ══════════════════════════════════════════════════════════════════
#  بنك أسئلة المسابقة الإسلامية — بالدارجة العاصمية
# ══════════════════════════════════════════════════════════════════
QUIZ_QUESTIONS = [
    {
        "id": 1,
        "q": "🧠 *سؤال إسلامي:*\nشكون هو أول نبي بعثو ربّنا سبحانه وتعالى؟",
        "opts": ["سيدنا نوح", "سيدنا آدم عليه السلام", "سيدنا إبراهيم", "سيدنا محمد ﷺ"],
        "ans": 1,
        "expl": "آدم عليه السلام هو أبو البشر وأول الأنبياء."
    },
    {
        "id": 2,
        "q": "🧠 *سؤال إسلامي:*\nقداش عدد السور اللي فيها القرآن الكريم؟",
        "opts": ["100 سورة", "110 سور", "114 سورة", "120 سورة"],
        "ans": 2,
        "expl": "القرآن الكريم فيه 114 سورة."
    },
    {
        "id": 3,
        "q": "🧠 *سؤال إسلامي:*\nفاش فُرضت الصلاة على المسلمين؟",
        "opts": ["في غزوة بدر", "في ليلة المعراج", "في أول يوم من رمضان", "في حجة الوداع"],
        "ans": 1,
        "expl": "فُرضت الصلاة في ليلة المعراج قبل الهجرة."
    },
    {
        "id": 4,
        "q": "🧠 *سؤال إسلامي:*\nشكون هو الصحابي اللي لقّبو رسول الله بـ \"الصديق\"؟",
        "opts": ["سيدنا عمر بن الخطاب", "سيدنا عثمان بن عفان", "سيدنا علي بن أبي طالب", "سيدنا أبو بكر الصديق"],
        "ans": 3,
        "expl": "سيدنا أبو بكر لقّبو النبي ﷺ بالصديق لأنو صدّقو في كل شيء."
    },
    {
        "id": 5,
        "q": "🧠 *سؤال إسلامي:*\nأيّ سورة تُسمّى \"أمّ الكتاب\" وتُقرأ في كل ركعة؟",
        "opts": ["سورة الإخلاص", "سورة الفاتحة", "سورة البقرة", "سورة يس"],
        "ans": 1,
        "expl": "سورة الفاتحة هي أم الكتاب وركن أساسي في كل ركعة."
    },
    {
        "id": 6,
        "q": "🧠 *سؤال إسلامي:*\nشكون اللي بنى الكعبة المشرّفة مع ولدو؟",
        "opts": ["سيدنا نوح وسام", "سيدنا إبراهيم وإسماعيل", "سيدنا موسى وهارون", "سيدنا داوود وسليمان"],
        "ans": 1,
        "expl": "سيدنا إبراهيم وابنو إسماعيل عليهم السلام بنيوا الكعبة المشرفة."
    },
    {
        "id": 7,
        "q": "🧠 *سؤال إسلامي:*\nأيّ سورة تُسمّى \"قلب القرآن\"؟",
        "opts": ["سورة البقرة", "سورة الكهف", "سورة يس", "سورة الرحمن"],
        "ans": 2,
        "expl": "سورة يس تُسمّى قلب القرآن كما جاء في الحديث الشريف."
    },
    {
        "id": 8,
        "q": "🧠 *سؤال إسلامي:*\nشكون هو الملاك المكلّف بإيصال الوحي للأنبياء؟",
        "opts": ["ميكائيل", "إسرافيل", "جبريل عليه السلام", "عزرائيل"],
        "ans": 2,
        "expl": "جبريل عليه السلام هو الملاك الأمين المكلّف بالوحي."
    },
    {
        "id": 9,
        "q": "🧠 *سؤال إسلامي:*\nكم سنة دامت الدعوة في مكة قبل الهجرة للمدينة؟",
        "opts": ["5 سنوات", "10 سنوات", "13 سنة", "20 سنة"],
        "ans": 2,
        "expl": "دامت الدعوة في مكة 13 سنة قبل الهجرة."
    },
    {
        "id": 10,
        "q": "🧠 *سؤال إسلامي:*\nأيّ آية تُسمّى \"سيّدة آيات القرآن\"؟",
        "opts": ["أول آية من الفاتحة", "آية الكرسي", "آخر آية من البقرة", "آية المداينة"],
        "ans": 1,
        "expl": "آية الكرسي هي سيدة آيات القرآن كما أخبر النبي ﷺ."
    },
    {
        "id": 11,
        "q": "🧠 *سؤال إسلامي:*\nفاش كان عمر النبي ﷺ وقتاش بدا يجيه الوحي؟",
        "opts": ["30 سنة", "35 سنة", "40 سنة", "45 سنة"],
        "ans": 2,
        "expl": "النبي ﷺ عندو 40 سنة بدا يجيه الوحي في غار حراء."
    },
    {
        "id": 12,
        "q": "🧠 *سؤال إسلامي:*\nشكون هي أول شهيدة في الإسلام؟",
        "opts": ["السيدة خديجة", "السيدة فاطمة", "سمية بنت خياط", "أسماء بنت أبي بكر"],
        "ans": 2,
        "expl": "سمية بنت خياط رضي الله عنها هي أول شهيدة في الإسلام."
    },
    {
        "id": 13,
        "q": "🧠 *سؤال إسلامي:*\nكم ركعة فصلاة الظهر؟",
        "opts": ["2 ركعات", "3 ركعات", "4 ركعات", "6 ركعات"],
        "ans": 2,
        "expl": "صلاة الظهر 4 ركعات."
    },
    {
        "id": 14,
        "q": "🧠 *سؤال إسلامي:*\nكم عدد أركان الإسلام؟",
        "opts": ["3 أركان", "4 أركان", "5 أركان", "6 أركان"],
        "ans": 2,
        "expl": "أركان الإسلام خمسة: الشهادتان، الصلاة، الزكاة، الصيام، الحج."
    },
    {
        "id": 15,
        "q": "🧠 *سؤال إسلامي:*\nأيّ سورة تُقرأ يوم الجمعة وتنوّر صاحبها من الجمعة للجمعة؟",
        "opts": ["سورة الملك", "سورة يس", "سورة الكهف", "سورة الواقعة"],
        "ans": 2,
        "expl": "سورة الكهف من قرأها يوم الجمعة أضاءت له نور من الجمعة للجمعة."
    },
    {
        "id": 16,
        "q": "🧠 *سؤال إسلامي:*\nفاين وُلد النبي محمد ﷺ؟",
        "opts": ["المدينة المنورة", "مكة المكرمة", "الطائف", "القدس"],
        "ans": 1,
        "expl": "النبي ﷺ وُلد في مكة المكرمة عام الفيل."
    },
    {
        "id": 17,
        "q": "🧠 *سؤال إسلامي:*\nشكون هو الجزائري اللي اشتهر بتلاوة القرآن بالرواية الورشية؟",
        "opts": ["الشيخ زكريا حمامة", "الشيخ ياسين الجزائري", "الشيخ سعيد دباح", "الشيخ منصور الوهراني"],
        "ans": 1,
        "expl": "الشيخ ياسين الجزائري معروف بتلاوته الرائعة بالرواية الورشية."
    },
    {
        "id": 18,
        "q": "🧠 *سؤال إسلامي:*\nكم آية في سورة الفاتحة؟",
        "opts": ["5 آيات", "6 آيات", "7 آيات", "8 آيات"],
        "ans": 2,
        "expl": "سورة الفاتحة فيها 7 آيات."
    },
    {
        "id": 19,
        "q": "🧠 *سؤال إسلامي:*\nشكون هو أطول سورة في القرآن الكريم؟",
        "opts": ["سورة آل عمران", "سورة البقرة", "سورة النساء", "سورة المائدة"],
        "ans": 1,
        "expl": "سورة البقرة هي أطول سورة في القرآن الكريم."
    },
    {
        "id": 20,
        "q": "🧠 *سؤال إسلامي:*\nفاش تصوم رمضان، قداش عدد أيامه في الغالب؟",
        "opts": ["28 يوم", "29 أو 30 يوم", "31 يوم", "27 يوم"],
        "ans": 1,
        "expl": "رمضان إما 29 أو 30 يوم حسب رؤية الهلال."
    },
]

QUIZ_BY_ID = {q["id"]: q for q in QUIZ_QUESTIONS}

RECITERS_PAGE_SIZE = 5   # قراء في كل صفحة
SURAHS_PAGE_SIZE  = 20  # سور في كل صفحة

RECITERS_BY_KEY = {r["key"]: r for r in ALGERIAN_RECITERS}

# ── بناء رابط الصوت ─────────────────────────────────────────────────────────
def build_audio_url(reciter: dict, surah_num: int, assabile_rec_id: str | None = None) -> str:
    src = reciter["source"]
    num = surah_num
    if src == "mp3quran":
        return f"{reciter['server']}/{num:03d}.mp3"
    if src == "archive":
        filename = DABBAH_FILES.get(surah_num, "")
        if not filename:
            return ""
        encoded = quote(filename, safe="")
        return f"https://archive.org/download/{DABBAH_ARCHIVE_ID}/{encoded}"
    if src == "assabile" and assabile_rec_id:
        slug = reciter["slug"]
        pid  = reciter["person_id"]
        return f"https://www.assabile.com/media/mp3/{slug}-{pid}/{assabile_rec_id}.mp3"
    return ""

# ── جلب قائمة السور من assabile AJAX (مزامن) ─────────────────────────────────
def fetch_assabile_surahs(reciter: dict) -> list[dict]:
    """يُرجع قائمة [{sura_id, name, rec_id}] أو [] عند الفشل."""
    pid = reciter["person_id"]
    col = reciter["collection_id"]
    url = f"https://ar.assabile.com/ajax/loadplayer-{pid}-{col}"
    try:
        res = requests.get(url, timeout=15).json()
        surahs = []
        for item in res.get("Recitation", []):
            sura_id = int(item.get("sura_id", 0))
            # اسم السورة من قائمتنا
            name = SURAH_NAMES[sura_id - 1] if 1 <= sura_id <= 114 else f"سورة {sura_id}"
            # href مثل "#3446" → "3446"
            rec_id = item.get("href", "#").lstrip("#")
            surahs.append({"sura_id": sura_id, "name": name, "rec_id": rec_id})
        # ترتيب حسب رقم السورة
        surahs.sort(key=lambda x: x["sura_id"])
        return surahs
    except Exception as e:
        logger.warning(f"assabile AJAX error for {reciter['key']}: {e}")
        return []

# ══════════════════════════════════════════════════════════════════
#  الولايات الـ 48
# ══════════════════════════════════════════════════════════════════
ALGERIA_STATES = {
    "1- أدرار":          (27.87, -0.29),
    "2- الشلف":          (36.16,  1.33),
    "3- الأغواط":        (33.80,  2.86),
    "4- أم البواقي":     (35.88,  7.11),
    "5- باتنة":          (35.56,  6.17),
    "6- بجاية":          (36.75,  5.06),
    "7- بسكرة":          (34.85,  5.73),
    "8- بشار":           (31.61, -2.22),
    "9- البليدة":        (36.47,  2.83),
    "10- البويرة":       (36.37,  3.91),
    "11- تمنراست":       (22.79,  5.52),
    "12- تبسة":          (35.40,  8.12),
    "13- تلمسان":        (34.88, -1.32),
    "14- تيارت":         (35.38,  1.32),
    "15- تيزي وزو":      (36.72,  4.05),
    "16- الجزائر":       (36.75,  3.05),
    "17- الجلفة":        (34.67,  3.25),
    "18- جيجل":          (36.82,  5.77),
    "19- سطيف":          (36.19,  5.41),
    "20- سعيدة":         (34.83,  0.15),
    "21- سكيكدة":        (36.87,  6.91),
    "22- سيدي بلعباس":   (35.19, -0.63),
    "23- عنابة":         (36.90,  7.77),
    "24- قالمة":         (36.46,  7.43),
    "25- قسنطينة":       (36.37,  6.61),
    "26- المدية":        (36.27,  2.75),
    "27- مستغانم":       (35.93,  0.09),
    "28- المسيلة":       (35.71,  4.54),
    "29- معسكر":         (35.40,  0.14),
    "30- ورقلة":         (31.95,  5.32),
    "31- وهران":         (35.69, -0.63),
    "32- البيض":         (33.68,  1.00),
    "33- إليزي":         (26.48,  8.49),
    "34- برج بوعريريج":  (36.07,  4.76),
    "35- بومرداس":       (36.76,  3.48),
    "36- الطارف":        (36.77,  8.31),
    "37- تندوف":         (27.67, -8.14),
    "38- تيسمسيلت":      (35.61,  1.82),
    "39- الوادي":        (33.37,  6.86),
    "40- خنشلة":         (35.44,  7.14),
    "41- سوق أهراس":     (36.28,  7.95),
    "42- تيبازة":        (36.61,  2.47),
    "43- ميلة":          (36.45,  6.26),
    "44- عين الدفلى":    (36.26,  1.97),
    "45- النعامة":       (33.27, -0.31),
    "46- عين تيموشنت":   (35.30, -1.14),
    "47- غرداية":        (32.49,  3.67),
    "48- غليزان":        (35.97,  0.57),
}

# ── لوحة المفاتيح الرئيسية ───────────────────────────────────────────────────
MAIN_KEYBOARD = [
    [KeyboardButton("🕌 مواقيت الصلاة"), KeyboardButton("📖 تصفح القرآن الكريم")],
    [KeyboardButton("📍 أقرب مسجد / حلال / مقهى", request_location=True)],
    [KeyboardButton("🧠 مسابقة إسلامية"), KeyboardButton("ℹ️ حول البوت")]
]

# ── المحتوى اليومي ───────────────────────────────────────────────────────────
DAILY_CONTENT = {
    "azkar_sabah":   "☀️ *أذكار الصباح:*\nأصبحنا وأصبح الملك لله والحمد لله..",
    "azkar_massa":   "🌆 *أذكار المساء:*\nأمسينا وأمسي الملك لله والحمد لله..",
    "daily_package": (
        "🌟 *المحتوى اليومي المتجدد:*\n\n"
        "📖 *آية:* ﴿وَمَن يَتَّقِ اللَّهَ يَجْعَل لَّهُ مَخْرَجًا﴾"
    ),
}

DUA_SADAQA = (
    "🤲 *دعاء صدقة جارية*\n\n"
    "اللهم اجعل هذا البوت صدقةً جاريةً عن صاحبته *الأخت الأندلسية*،\n"
    "اللهم اغفر لها وارحمها وتقبّل منها،\n"
    "وبارك الله في ابنتها وجعلها قرةَ عينٍ لها ولوالدها المجاهد في أرض جزيرة محمد،\n"
    "اللهم احفظهم وانصرهم وثبّت أقدامهم. آمين 🇩🇿"
)


# ══════════════════════════════════════════════════════════════════
#  بداية البوت
# ══════════════════════════════════════════════════════════════════
def _register_quiz_user(user, chat_id: int):
    """يسجّل المستخدم في المسابقة التلقائية عند أول تواصل."""
    db["quiz"].add(chat_id)
    if chat_id not in db["quiz_scores"]:
        db["quiz_scores"][chat_id] = {
            "name":    (user.first_name or "مجهول")[:30],
            "correct": 0,
            "total":   0,
        }
        save_db()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    _register_quiz_user(user, chat_id)

    await update.message.reply_text(
        f"واش راك يا {user.first_name}؟ 👋\n"
        "مرحبا بيك في *البوت الإسلامي الدزايري* 🇩🇿\n\n"
        "💡 *واش يقدر يعمل البوت هادا:*\n\n"
        "🕌 مواقيت الصلاة لـ 48 ولاية دزايرية\n"
        "📖 تصفح القرآن واسمع بصوت قراء دزايريين\n"
        "📍 ارسل موقعك باش تعرف أقرب مسجد ومحل حلال\n"
        "🧠 مسابقة إسلامية كل ساعتين — *مسجّل تلقائياً* ✅\n"
        "🏆 لوحة الأوائل كل خميس ليلاً — المتصدّر يحظى بتكريم خاص 🎖\n"
        "🕒 أذكار الصباح والمساء والمحتوى اليومي\n\n"
        "🔧 *الأوامر المتاحة:*\n"
        "• `/alarm اسم_الولاية` — تفعيل تنبيه الأذان\n"
        "• `/auto` — تفعيل الأذكار والمحتوى اليومي\n"
        "• `/quiz` — شوف لوحة الأوائل\n"
        "• `/stop` — إيقاف التنبيهات (المسابقة تبقى)\n\n"
        "يرحم والديك 🤲 — حظّ سعيد في المسابقة! 🏅",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════════════
#  مواقيت الصلاة
# ══════════════════════════════════════════════════════════════════
def get_prayer_times(lat: float, lon: float) -> dict | None:
    date = datetime.now().strftime("%d-%m-%Y")
    url = (
        f"https://api.aladhan.com/v1/timings/{date}"
        f"?latitude={lat}&longitude={lon}&method=21"
    )
    try:
        res = requests.get(url, timeout=10).json()
        return res["data"]["timings"] if res.get("code") == 200 else None
    except Exception:
        return None


async def prayer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(state, callback_data=f"pray|{state}")]
        for state in ALGERIA_STATES.keys()
    ]
    await update.message.reply_text(
        "📌 اختر ولايتك لعرض مواقيت الصلاة الحالية:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def prayer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    state_name = query.data.split("|", 1)[1]
    lat, lon = ALGERIA_STATES[state_name]
    times = get_prayer_times(lat, lon)
    if times:
        text = (
            f"🕌 مواقيت الصلاة في ولاية ({state_name})\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"🌅 الفجر:   {times['Fajr']}\n"
            f"☀️ الشروق: {times['Sunrise']}\n"
            f"🕌 الظهر:   {times['Dhuhr']}\n"
            f"🌆 العصر:   {times['Asr']}\n"
            f"🌅 المغرب:  {times['Maghrib']}\n"
            f"🌃 العشاء:  {times['Isha']}"
        )
        await query.edit_message_text(text)
    else:
        await query.edit_message_text("❌ عذراً، تعذر جلب المواقيت حالياً.")


async def check_prayer_alarms(app):
    now_str = datetime.now().strftime("%H:%M")
    for chat_id, state in list(db["alarms"].items()):
        lat, lon = ALGERIA_STATES.get(state, (36.75, 3.05))
        times = get_prayer_times(lat, lon)
        if times:
            for prayer, p_time in times.items():
                if prayer in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"] and p_time == now_str:
                    try:
                        await app.bot.send_message(
                            chat_id,
                            f"🕌 حان الآن موعد آذان صلاة *{prayer}* "
                            f"حسب توقيت ولاية {state} 🇩🇿",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass


async def set_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = " ".join(context.args)
    if not state:
        return await update.message.reply_text(
            "⚠️ يرجى كتابة اسم الولاية بعد الأمر. مثال:\n`/alarm 16- الجزائر`",
            parse_mode="Markdown"
        )
    matched = next((s for s in ALGERIA_STATES if state in s), None)
    if matched:
        db["alarms"][update.effective_chat.id] = matched
        save_db()
        await update.message.reply_text(f"🔔 تم تفعيل تنبيهات الأذان لولاية: {matched}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الولاية.")


# ══════════════════════════════════════════════════════════════════
#  قسم القرآن الكريم — القراء الجزائريون
# ══════════════════════════════════════════════════════════════════

def reciters_keyboard(page: int) -> InlineKeyboardMarkup:
    """لوحة اختيار القارئ مع ترقيم الصفحات."""
    start = page * RECITERS_PAGE_SIZE
    end   = start + RECITERS_PAGE_SIZE
    chunk = ALGERIAN_RECITERS[start:end]

    rows = []
    for r in chunk:
        rows.append([InlineKeyboardButton(
            f"🎙 {r['name']} ({r['riwaya']})",
            callback_data=f"reciter|{r['key']}|0"
        )])

    # أزرار التنقل بين الصفحات
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"reciters_page|{page-1}"))
    total_pages = (len(ALGERIAN_RECITERS) + RECITERS_PAGE_SIZE - 1) // RECITERS_PAGE_SIZE
    if end < len(ALGERIAN_RECITERS):
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"reciters_page|{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(
        f"📄 الصفحة {page+1}/{total_pages}", callback_data="noop"
    )])
    return InlineKeyboardMarkup(rows)


def surahs_keyboard(reciter_key: str, surahs: list, page: int) -> InlineKeyboardMarkup:
    """لوحة اختيار السورة مع ترقيم الصفحات."""
    start = page * SURAHS_PAGE_SIZE
    end   = start + SURAHS_PAGE_SIZE
    chunk = surahs[start:end]

    rows = []
    # 2 سورتان في كل صف
    for i in range(0, len(chunk), 2):
        row = []
        for item in chunk[i:i+2]:
            sura_id = item["sura_id"]
            name    = item["name"]
            rec_id  = item.get("rec_id", "")
            cd      = f"surah|{reciter_key}|{sura_id}|{rec_id}"
            row.append(InlineKeyboardButton(f"{sura_id}. {name}", callback_data=cd))
        rows.append(row)

    # أزرار التنقل
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"surahs_page|{reciter_key}|{page-1}"))
    total_pages = (len(surahs) + SURAHS_PAGE_SIZE - 1) // SURAHS_PAGE_SIZE
    if end < len(surahs):
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"surahs_page|{reciter_key}|{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(f"📄 الصفحة {page+1}/{total_pages}", callback_data="noop")])
    rows.append([InlineKeyboardButton("🔙 القائمة الرئيسية للقراء", callback_data="reciters_page|0")])
    return InlineKeyboardMarkup(rows)


def get_reciter_surahs(reciter: dict) -> list[dict]:
    """يُرجع قائمة السور المتاحة للقارئ (من الكاش أو يجلبها)."""
    key = reciter["key"]
    if key in db["surah_cache"]:
        return db["surah_cache"][key]

    if reciter["source"] == "assabile":
        surahs = fetch_assabile_surahs(reciter)
    elif reciter["source"] == "archive":
        # سعيد دباح: السور المتاحة مخزّنة في DABBAH_FILES
        surahs = [
            {"sura_id": n, "name": SURAH_NAMES[n-1], "rec_id": ""}
            for n in sorted(DABBAH_FILES.keys())
        ]
    else:
        # mp3quran: نبني القائمة من الأرقام المخزّنة
        surahs = [
            {"sura_id": n, "name": SURAH_NAMES[n-1], "rec_id": ""}
            for n in reciter["surahs"]
        ]

    db["surah_cache"][key] = surahs
    return surahs


# ── عرض قائمة القراء ────────────────────────────────────────────────────────
async def quran_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *القرآن الكريم بأصوات قراء جزائريين*\n\n"
        "اختر القارئ للاستماع إلى تلاواته:",
        reply_markup=reciters_keyboard(0),
        parse_mode="Markdown"
    )


async def reciters_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("|")[1])
    await query.edit_message_text(
        "📖 *القرآن الكريم بأصوات قراء جزائريين*\n\nاختر القارئ:",
        reply_markup=reciters_keyboard(page),
        parse_mode="Markdown"
    )


# ── عرض قائمة السور للقارئ ──────────────────────────────────────────────────
async def reciter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, reciter_key, page_str = query.data.split("|")
    page = int(page_str)
    reciter = RECITERS_BY_KEY.get(reciter_key)
    if not reciter:
        await query.answer("❌ قارئ غير معروف", show_alert=True)
        return

    await query.edit_message_text(
        f"⏳ جارٍ تحميل قائمة السور بصوت {reciter['name']}...",
        parse_mode="Markdown"
    )

    surahs = get_reciter_surahs(reciter)
    if not surahs:
        await query.edit_message_text(
            f"❌ تعذر جلب قائمة السور للشيخ {reciter['name']}. حاول مرة أخرى."
        )
        return

    await query.edit_message_text(
        f"📖 *{reciter['name']}*\n"
        f"📻 الرواية: {reciter['riwaya']}\n"
        f"📂 {len(surahs)} سورة متاحة\n\n"
        "اختر السورة للاستماع:",
        reply_markup=surahs_keyboard(reciter_key, surahs, page),
        parse_mode="Markdown"
    )


async def surahs_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, reciter_key, page_str = query.data.split("|")
    page = int(page_str)
    reciter = RECITERS_BY_KEY.get(reciter_key)
    surahs  = get_reciter_surahs(reciter)

    await query.edit_message_text(
        f"📖 *{reciter['name']}* — اختر السورة:",
        reply_markup=surahs_keyboard(reciter_key, surahs, page),
        parse_mode="Markdown"
    )


# ── إرسال الملف الصوتي ───────────────────────────────────────────────────────
async def surah_audio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎵 جارٍ تحميل الصوت...")
    parts = query.data.split("|")          # surah|key|sura_id|rec_id
    reciter_key = parts[1]
    sura_id     = int(parts[2])
    rec_id      = parts[3] if len(parts) > 3 else ""
    reciter     = RECITERS_BY_KEY.get(reciter_key)

    if not reciter:
        await query.message.reply_text("❌ قارئ غير معروف.")
        return

    audio_url = build_audio_url(reciter, sura_id, rec_id or None)
    surah_name = SURAH_NAMES[sura_id - 1]

    if not audio_url:
        await query.message.reply_text(
            f"❌ لا يوجد رابط صوتي لسورة {surah_name} عند هذا القارئ."
        )
        return

    try:
        await query.message.reply_audio(
            audio=audio_url,
            title=f"سورة {surah_name}",
            performer=reciter["name"],
            caption=f"📖 سورة *{surah_name}* — {reciter['name']}\n📻 {reciter['riwaya']}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Audio send error ({reciter_key} / {sura_id}): {e}")
        await query.message.reply_text(
            f"❌ تعذر إرسال الملف الصوتي لسورة {surah_name}.\n"
            f"يمكنك الاستماع مباشرة من الرابط:\n{audio_url}"
        )


# ══════════════════════════════════════════════════════════════════
#  أقرب مسجد / حلال / مقهى
# ══════════════════════════════════════════════════════════════════
async def find_nearby_places(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude
    await update.message.reply_text("🔄 جارٍ البحث عن أقرب المساجد والمحلات الحلال والمقاهي...")
    overpass_query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="place_of_worship"]["religion"="islam"]({lat-0.03},{lon-0.03},{lat+0.03},{lon+0.03});
      node["diet:halal"="yes"]({lat-0.03},{lon-0.03},{lat+0.03},{lon+0.03});
      node["shop"="butcher"]["halal"="yes"]({lat-0.03},{lon-0.03},{lat+0.03},{lon+0.03});
      node["amenity"="cafe"]({lat-0.03},{lon-0.03},{lat+0.03},{lon+0.03});
    );
    out body 10;
    """
    try:
        res = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": overpass_query}, timeout=30
        ).json()
        elements = res.get("elements", [])
        if not elements:
            return await update.message.reply_text("📍 لم نتمكن من العثور على مرافق قريبة.")
        response_text = "📍 *النتائج القريبة منك:*\n\n"
        for idx, el in enumerate(elements, 1):
            tags     = el.get("tags", {})
            name     = tags.get("name", "مرفق غير مسمى")
            amenity  = tags.get("amenity", tags.get("shop", "محل"))
            icon     = "🕌" if amenity == "place_of_worship" else ("☕" if amenity == "cafe" else "🥩")
            p_lat, p_lon = el["lat"], el["lon"]
            map_link = f"https://www.google.com/maps?q={p_lat},{p_lon}"
            lon1, lat1, lon2, lat2 = map(radians, [lon, lat, p_lon, p_lat])
            dist = 2 * 6371 * asin(
                sqrt(sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2)
            )
            response_text += (
                f"{idx}. {icon} *{name}*\n"
                f"📏 {dist:.2f} كم — 🔗 [افتح على الخريطة]({map_link})\n\n"
            )
        await update.message.reply_text(
            response_text, parse_mode="Markdown", disable_web_page_preview=True
        )
    except Exception:
        await update.message.reply_text("❌ حدث خطأ أثناء الاتصال بخدمة الخرائط.")


# ══════════════════════════════════════════════════════════════════
#  الإرسال التلقائي والمحتوى اليومي
# ══════════════════════════════════════════════════════════════════
async def start_auto_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db["auto"].add(update.effective_chat.id)
    save_db()
    await update.message.reply_text("🕒 تم تفعيل الإرسال التلقائي بنجاح!")


async def stop_all_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db["alarms"].pop(chat_id, None)
    db["auto"].discard(chat_id)
    save_db()
    await update.message.reply_text("🔕 تم إيقاف كافة التنبيهات.")


async def send_sabah_content(app):
    for chat_id in list(db["auto"]):
        try:
            await app.bot.send_message(chat_id, DAILY_CONTENT["azkar_sabah"], parse_mode="Markdown")
        except Exception:
            pass


async def send_daily_package(app):
    for chat_id in list(db["auto"]):
        try:
            await app.bot.send_message(chat_id, DAILY_CONTENT["daily_package"], parse_mode="Markdown")
        except Exception:
            pass


async def send_massa_content(app):
    for chat_id in list(db["auto"]):
        try:
            await app.bot.send_message(chat_id, DAILY_CONTENT["azkar_massa"], parse_mode="Markdown")
        except Exception:
            pass


async def send_dua_sadaqa(app):
    for chat_id in list(db["auto"]):
        try:
            await app.bot.send_message(chat_id, DUA_SADAQA, parse_mode="Markdown")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
#  المسابقة الإسلامية
# ══════════════════════════════════════════════════════════════════
def build_leaderboard_text() -> str:
    """بناء نص لوحة الأوائل."""
    scores = db["quiz_scores"]
    if not scores:
        return "🏆 لوحة الأوائل فارغة بعد — حل بعض الأسئلة وارجع!"

    ranked = sorted(scores.values(), key=lambda x: x["correct"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *لوحة أوائل المسابقة الإسلامية الدزايرية* 🇩🇿\n"]
    for i, entry in enumerate(ranked[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        total = entry["total"] or 1
        pct   = int(entry["correct"] / total * 100)
        lines.append(
            f"{medal} *{entry['name']}* — {entry['correct']} صح / {entry['total']} سؤال ({pct}%)"
        )
    return "\n".join(lines)


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /quiz — عرض لوحة الأوائل (المسابقة إجبارية للكل)."""
    text = build_leaderboard_text()
    await update.message.reply_text(text, parse_mode="Markdown")


async def quiz_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر '🧠 مسابقة إسلامية' من لوحة المفاتيح — يرسل سؤالاً فورياً."""
    await send_single_quiz(update.effective_chat.id, update.get_bot())


async def send_quiz(app):
    """جدولة: ترسل سؤالاً عشوائياً لكل المشتركين كل ساعتين."""
    q = random.choice(QUIZ_QUESTIONS)
    markup = _quiz_keyboard(q)
    recipients = db["auto"] | db["quiz"]
    for chat_id in list(recipients):
        try:
            await app.bot.send_message(
                chat_id,
                q["q"] + "\n\n_اختر الجواب الصحيح 👇_",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception:
            pass


async def send_single_quiz(chat_id: int, bot):
    """يرسل سؤالاً عشوائياً لشخص واحد (عند الضغط على الزر)."""
    q = random.choice(QUIZ_QUESTIONS)
    markup = _quiz_keyboard(q)
    try:
        await bot.send_message(
            chat_id,
            q["q"] + "\n\n_اختر الجواب الصحيح 👇_",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"send_single_quiz error: {e}")


def _quiz_keyboard(q: dict) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(q["opts"]):
        rows.append([InlineKeyboardButton(
            opt, callback_data=f"quiz|{q['id']}|{i}"
        )])
    return InlineKeyboardMarkup(rows)


async def quiz_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()          # إيقاف أيقونة التحميل على الفور
    _, q_id_str, chosen_str = query.data.split("|")
    q = QUIZ_BY_ID.get(int(q_id_str))
    if not q:
        await query.message.reply_text("❌ السؤال ما لقيناهوش.")
        return
    chosen  = int(chosen_str)
    correct = q["ans"]
    chat_id = query.message.chat_id
    user    = query.from_user

    # ── تحديث النقاط ────────────────────────────────────────────────
    if chat_id not in db["quiz_scores"]:
        db["quiz_scores"][chat_id] = {
            "name":    (user.first_name or "مجهول")[:30],
            "correct": 0,
            "total":   0,
        }
    db["quiz_scores"][chat_id]["total"] += 1
    if chosen == correct:
        db["quiz_scores"][chat_id]["correct"] += 1
        verdict = "✅ *صحّ! إجابتك صحيحة* 🎉"
    else:
        verdict = (
            f"❌ *غلطت!*\n"
            f"الجواب الصحيح هو: *{q['opts'][correct]}*"
        )
    save_db()

    # ── تعديل رسالة السؤال بالنتيجة (تبقى ظاهرة بدل ما تختفي) ────────
    result_text = (
        f"{q['q']}\n\n"
        f"{verdict}\n\n"
        f"📝 {q['expl']}"
    )
    try:
        await query.message.edit_text(result_text, parse_mode="Markdown")
    except Exception:
        await query.message.reply_text(result_text, parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════════
#  منشورات الحداد — حرائق الغابات الجزائرية (3 أيام)
#  تاريخ البدء: 22 يوليو 2026
# ══════════════════════════════════════════════════════════════════
from datetime import date as _date

MOURNING_START = _date(2026, 7, 22)   # أول يوم حداد
MOURNING_DAYS  = 3                    # مدة الحداد

MOURNING_POSTS = [
    # اليوم الأول
    (
        "🇩🇿 *إنّا لله وإنّا إليه راجعون*\n\n"
        "﴿وَبَشِّرِ الصَّابِرِينَ ۝ الَّذِينَ إِذَا أَصَابَتْهُم مُّصِيبَةٌ قَالُوا إِنَّا لِلَّهِ وَإِنَّا إِلَيْهِ رَاجِعُونَ﴾\n\n"
        "قلوبنا مع إخواننا في الولايات المتضرّرة من حرائق الغابات… "
        "نشاركهم ألمهم ونحمل معهم همّهم.\n\n"
        "🤲 اللهم اجعل هذه النار برداً وسلاماً على أهلنا، "
        "وارحم شهداءنا، واشفِ جرحانا، وأعِد لهم ما فقدوه أضعافاً مضاعفة.\n\n"
        "🕯 *يوم الحداد الأول — نحن معكم يا أهل الجزائر* 🇩🇿\n\n"
        "_هذا البوت صدقة جارية يديره شباب جزائري يواسي إخوانه في المحن._"
    ),
    # اليوم الثاني
    (
        "🇩🇿 *تضامن — حرائق الغابات الجزائرية*\n\n"
        "قال النبي ﷺ: «مَثَلُ المُؤمِنِينَ في تَوادِّهِم وتَراحُمِهِم وتَعاطُفِهِم، "
        "مَثَلُ الجَسَدِ، إذا اشتَكى مِنهُ عُضوٌ تَداعى له سائرُ الجَسَدِ بالسَّهَرِ والحُمَّى»\n\n"
        "أهلنا في الغابات يُجاهدون النار، ونحن نُجاهد معهم بالدعاء والتضامن.\n\n"
        "🤲 اللهم أنزِل عليهم رحمتك، وكُن لهم عوناً وسنداً، "
        "وارزقهم الصبر والثبات، وعوّضهم خيراً مما أُصيبوا به.\n\n"
        "🕯 *يوم الحداد الثاني — الجزائر في قلوبنا* 🇩🇿\n\n"
        "_هذا البوت صدقة جارية يديره شباب جزائري يواسي إخوانه في المحن._"
    ),
    # اليوم الثالث
    (
        "🇩🇿 *دعاء الختام — ثالث أيام الحداد*\n\n"
        "«اللهم إنَّا نسألك بأسمائك الحسنى وصفاتك العُلا أن تُطفئ هذه النيران، "
        "وأن تُحيي ما أحرقته بنباتٍ وخير، "
        "وأن تشفي جرحانا وترحم شهداءنا وتُعوّض المتضرّرين.»\n\n"
        "ثلاثة أيام مرّت ونحن نحمل في قلوبنا جرح إخواننا… "
        "الجزائر لا تُكسر، وشعبها لا يُهزم بإذن الله.\n\n"
        "🌿 اللهم اجعل مكان الرماد خضرةً وحياة، "
        "وأعِد لأهلنا أجمل مما فقدوا.\n\n"
        "🕯 *يوم الحداد الثالث — وقفة وفاء لأرواح الشهداء* 🇩🇿\n\n"
        "_هذا البوت صدقة جارية يديره شباب جزائري يواسي إخوانه في المحن._"
    ),
]


async def send_mourning_post(app):
    """ينشر منشور الحداد المناسب للمشتركين خلال 3 أيام."""
    today     = _date.today()
    day_index = (today - MOURNING_START).days
    if day_index < 0 or day_index >= MOURNING_DAYS:
        return                   # خارج فترة الحداد
    text       = MOURNING_POSTS[day_index]
    recipients = db["auto"] | db["quiz"]
    for chat_id in list(recipients):
        try:
            await app.bot.send_message(chat_id, text, parse_mode="Markdown")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
#  لوحة الأوائل الأسبوعية — كل خميس
# ══════════════════════════════════════════════════════════════════
async def send_weekly_leaderboard(app):
    """يُرسل لوحة الأوائل كل خميس ليلاً لجميع المشتركين."""
    scores = db["quiz_scores"]
    if not scores:
        return

    ranked = sorted(scores.values(), key=lambda x: x["correct"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines  = ["🏆 *لوحة أوائل المسابقة الإسلامية — نتائج هذا الأسبوع* 🇩🇿\n"]
    for i, entry in enumerate(ranked[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        total = entry["total"] or 1
        pct   = int(entry["correct"] / total * 100)
        lines.append(
            f"{medal} *{entry['name']}* — {entry['correct']} صح / {entry['total']} سؤال ({pct}%)"
        )

    # تكريم المتصدّر
    winner = ranked[0]
    lines.append(
        f"\n🎖 *مبروك للمتصدّر {winner['name']}!* 🎉\n"
        "أنت نجم المسابقة هذا الأسبوع، بارك الله فيك وزادك علماً 🌟"
    )
    text = "\n".join(lines)

    recipients = db["auto"] | db["quiz"]
    for chat_id in list(recipients):
        try:
            await app.bot.send_message(chat_id, text, parse_mode="Markdown")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
#  حول البوت
# ══════════════════════════════════════════════════════════════════
async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *حول البوت الإسلامي الجزائري* 🇩🇿\n\n"
        "بوت متكامل يخدم المسلمين الجزائريين بمواقيت الصلاة\n"
        "والقرآن الكريم بأصوات قراء جزائريين والأذكار اليومية.",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════════════
#  نقطة الانطلاق
# ══════════════════════════════════════════════════════════════════
def main():
    if not TOKEN:
        raise RuntimeError("يرجى ضبط TELEGRAM_BOT_TOKEN في متغيرات البيئة")

    app = Application.builder().token(TOKEN).build()

    # ── الجدولة ──────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Africa/Algiers")
    scheduler.add_job(check_prayer_alarms,     "interval", minutes=1,                              args=[app])
    scheduler.add_job(send_sabah_content,      CronTrigger(hour=6,  minute=0),                    args=[app])
    scheduler.add_job(send_daily_package,      CronTrigger(hour=8,  minute=0),                    args=[app])
    scheduler.add_job(send_massa_content,      CronTrigger(hour=17, minute=0),                    args=[app])
    scheduler.add_job(send_dua_sadaqa,         CronTrigger(hour=21, minute=0),                    args=[app])
    scheduler.add_job(send_quiz,               "interval", hours=2,                               args=[app])
    # لوحة الأوائل كل خميس الساعة 21:00
    scheduler.add_job(send_weekly_leaderboard, CronTrigger(day_of_week="thu", hour=21, minute=0), args=[app])
    # منشورات الحداد — يُرسَل يومياً الساعة 10:00 صباحاً (3 أيام فقط)
    scheduler.add_job(send_mourning_post,      CronTrigger(hour=10, minute=0),                   args=[app])
    scheduler.start()

    # ── الأوامر ───────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alarm", set_alarm))
    app.add_handler(CommandHandler("auto",  start_auto_broadcast))
    app.add_handler(CommandHandler("quiz",  show_leaderboard))
    app.add_handler(CommandHandler("stop",  stop_all_services))

    # ── الرسائل النصية ────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.Text(["🕌 مواقيت الصلاة"]),        prayer_menu))
    app.add_handler(MessageHandler(filters.Text(["📖 تصفح القرآن الكريم"]),  quran_menu))
    app.add_handler(MessageHandler(filters.Text(["🧠 مسابقة إسلامية"]),      quiz_menu))
    app.add_handler(MessageHandler(filters.Text(["ℹ️ حول البوت"]),            about_bot))
    app.add_handler(MessageHandler(filters.LOCATION,                           find_nearby_places))

    # ── الأزرار التفاعلية ─────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(prayer_callback,       pattern=r"^pray\|"))
    app.add_handler(CallbackQueryHandler(reciters_page_callback, pattern=r"^reciters_page\|"))
    app.add_handler(CallbackQueryHandler(reciter_callback,       pattern=r"^reciter\|"))
    app.add_handler(CallbackQueryHandler(surahs_page_callback,   pattern=r"^surahs_page\|"))
    app.add_handler(CallbackQueryHandler(surah_audio_callback,   pattern=r"^surah\|"))
    app.add_handler(CallbackQueryHandler(quiz_answer_callback,   pattern=r"^quiz\|"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))

    app.run_polling()


if __name__ == "__main__":
    main()
