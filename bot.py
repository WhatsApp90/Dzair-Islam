import os
import json
import logging
import random
import requests
import asyncio
from urllib.parse import quote
from math import radians, cos, sin, asin, sqrt
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.error import TelegramError
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
        "alarms":         {},
        "auto":           [],
        "quiz":           [],
        "quiz_scores":    {},
        "surah_cache":    {},
        "broadcast_sent": False,  # للتحقق من إرسال رسالة التحديث
    }
    if not os.path.exists(DB_FILE):
        return default
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # تحويل المفاتيح الرقمية من string إلى int
        data["alarms"]            = {int(k): v for k, v in data.get("alarms", {}).items()}
        data["quiz_scores"]       = {int(k): v for k, v in data.get("quiz_scores", {}).items()}
        data["auto"]              = data.get("auto", [])
        data["quiz"]              = data.get("quiz", [])
        data["surah_cache"]       = data.get("surah_cache", {})
        data["broadcast_sent"]    = data.get("broadcast_sent", False)
        data["broadcast_version"] = data.get("broadcast_version", 0)
        return data
    except Exception as e:
        logger.error(f"خطأ في تحميل البيانات: {e}")
        return default

def save_db():
    """حفظ البيانات في الملف (بدون surah_cache لأنها مؤقتة).
       الأرقام المحمية تُضاف دائماً قبل الحفظ."""
    # ضمان الأرقام المحمية في القوائم قبل الحفظ
    auto_list = list(db["auto"] | PROTECTED_IDS)
    quiz_list = list(db["quiz"] | PROTECTED_IDS)
    for pid in PROTECTED_IDS:
        if pid not in db["quiz_scores"]:
            db["quiz_scores"][pid] = {"name": "محمي", "correct": 0, "total": 0}
    try:
        data = {
            "alarms":            db["alarms"],
            "auto":              auto_list,
            "quiz":              quiz_list,
            "quiz_scores":       db["quiz_scores"],
            "broadcast_sent":    db.get("broadcast_sent", False),
            "broadcast_version": db.get("broadcast_version", 0),
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ البيانات: {e}")

# ══════════════════════════════════════════════════════════════════
#  أرقام ID المحمية — لا تُحذف أبداً مهما تم من تحديث أو إعادة تشغيل
# ══════════════════════════════════════════════════════════════════
PROTECTED_IDS: set[int] = {6856665810, 8955506857, 8688282197}

# رقم الإصدار — غيّره لإعادة إرسال رسالة التحديث تلقائياً
BROADCAST_VERSION = 2

# ── تحميل البيانات وتحويل القوائم إلى sets ───────────────────────────────────
_raw = load_db()
db = {
    "alarms":            _raw["alarms"],
    "auto":              set(_raw["auto"]),
    "quiz":              set(_raw["quiz"]),
    "quiz_scores":       _raw["quiz_scores"],
    "surah_cache":       {},
    "broadcast_sent":    _raw.get("broadcast_sent", False),
    "broadcast_version": _raw.get("broadcast_version", 0),
}

def ensure_protected_ids():
    """يضمن دائماً وجود الأرقام المحمية في كل قوائم الاشتراك."""
    changed = False
    for pid in PROTECTED_IDS:
        if pid not in db["auto"]:
            db["auto"].add(pid)
            changed = True
        if pid not in db["quiz"]:
            db["quiz"].add(pid)
            changed = True
        if pid not in db["quiz_scores"]:
            db["quiz_scores"][pid] = {"name": "محمي", "correct": 0, "total": 0}
            changed = True
    if changed:
        save_db()

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
# ══════════════════════════════════════════════════════════════════
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
        "collection_id": 531,
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
#  بنك أسئلة المسابقة الإسلامية المطور — بالدارجة الجزائرية
# ══════════════════════════════════════════════════════════════════
QUIZ_QUESTIONS = [
    {
        "id": 1,
        "q": "🧠 *سؤال دزايري:* \nشكون هو أول نبي بعثو ربّنا سبحانه وتعالى للأرض؟",
        "opts": ["سيدنا نوح", "سيدنا آدم عليه السلام", "سيدنا إبراهيم", "سيدنا محمد ﷺ"],
        "ans": 1,
        "expl": "سيدنا آدم عليه السلام هو أبو البشر وأول الأنبياء."
    },
    {
        "id": 2,
        "q": "🧠 *سؤال دزايري:* \nشحال كاين من سورة في القرآن الكريم كامل؟",
        "opts": ["100 سورة", "110 سور", "114 سورة", "120 سورة"],
        "ans": 2,
        "expl": "القرآن الكريم فيه 114 سورة."
    },
    {
        "id": 3,
        "q": "🧠 *سؤال دزايري:* \nوينتا تفايضت وفرض ربي الصلاة على المسلمين؟",
        "opts": ["في غزوة بدر", "في ليلة الإسراء والمعراج", "في أول يوم رمضان", "في حجة الوداع"],
        "ans": 1,
        "expl": "فُرضت الصلاة فوق 7 سموات في ليلة الإسراء والمعراج."
    },
    {
        "id": 4,
        "q": "🧠 *سؤال دزايري:* \nشكون الصحابي الجليل اللي سماه النبي ﷺ بـ \"الصديق\"؟",
        "opts": ["سيدنا عمر بن الخطاب", "سيدنا عثمان بن عفان", "سيدنا علي بن أبي طالب", "سيدنا أبو بكر الصديق"],
        "ans": 3,
        "expl": "سيدنا أبو بكر رضي الله عنه سمي بالصديق لأنه صدّق النبي ﷺ فوراً في خبر الإسراء والمعراج."
    },
    {
        "id": 5,
        "q": "🧠 *سؤال دزايري:* \nشكون السورة اللي يتسماوها \"أمّ الكتاب\" وبلا بيها الصلاة ما تقبلش؟",
        "opts": ["سورة الإخلاص", "سورة الفاتحة", "سورة البقرة", "سورة يس"],
        "ans": 1,
        "expl": "سورة الفاتحة هي أم القرآن وركن أساسي في كل ركعة."
    },
    {
        "id": 6,
        "q": "🧠 *سؤال دزايري:* \nشكون النبي اللي بنى الكعبة المشرفة مع ولدو؟",
        "opts": ["سيدنا نوح وسام", "سيدنا إبراهيم وإسماعيل", "سيدنا موسى وهارون", "سيدنا داوود وسليمان"],
        "ans": 1,
        "expl": "سيدنا إبراهيم الخليل وابنو إسماعيل عليهما السلام هما اللي بناوا قواعد البيت الحرام."
    },
    {
        "id": 7,
        "q": "🧠 *سؤال دزايري:* \nشكون السورة اللي معرّفة بـ \"قلب القرآن\"؟",
        "opts": ["سورة البقرة", "سورة الكهف", "سورة يس", "سورة الرحمن"],
        "ans": 2,
        "expl": "سورة يس تسمى قلب القرآن كما ورد في الأثر."
    },
    {
        "id": 8,
        "q": "🧠 *سؤال دزايري:* \nشكون الملك المكلّف بإيصال الوحي من ربي للأنبياء؟",
        "opts": ["ميكائيل", "إسرافيل", "جبريل عليه السلام", "ملك الموت"],
        "ans": 2,
        "expl": "سيدنا جبريل عليه السلام هو أمين الوحي."
    },
    {
        "id": 9,
        "q": "🧠 *سؤال دزايري:* \nشحال قعدت الدعوة الإسلامية في مكة قبل الهجرة للمدينة؟",
        "opts": ["5 سنين", "10 سنين", "13 سنة", "20 سنة"],
        "ans": 2,
        "expl": "دامت الدعوة في مكة المكرمة 13 سنة."
    },
    {
        "id": 10,
        "q": "🧠 *سؤال دزايري:* \nشكون الآية العظيمة اللي تتسمى \"سيدة آيات القرآن\"؟",
        "opts": ["أول آية في الفاتحة", "آية الكرسي", "خواتيم سورة البقرة", "آية الدين"],
        "ans": 1,
        "expl": "آية الكرسي هي أعظم آية في كتاب الله."
    },
    {
        "id": 11,
        "q": "🧠 *سؤال دزايري:* \nشحال كان عمر سيدنا النبي ﷺ نهار هبط عليه الوحي أول مرة؟",
        "opts": ["30 سنة", "35 سنة", "40 سنة", "45 سنة"],
        "ans": 2,
        "expl": "نزل الوحي على النبي ﷺ وهو في عمر 40 سنة بغار حراء."
    },
    {
        "id": 12,
        "q": "🧠 *سؤال دزايري:* \nشكون هي أول امرأة استشهدت في الإسلام؟",
        "opts": ["خديجة بنت خويلد", "فاطمة الزهراء", "سمية بنت خياط", "أسماء بنت أبي بكر"],
        "ans": 2,
        "expl": "أم عمار بن ياسر (سمية بنت خياط رضي الله عنها) هي أول شهيدة في الإسلام."
    },
    {
        "id": 13,
        "q": "🧠 *سؤال دزايري:* \nشحال عدد ركعات صلاة الظهر في الأصل؟",
        "opts": ["2 ركعات", "3 ركعات", "4 ركعات", "6 ركعات"],
        "ans": 2,
        "expl": "صلاة الظهر تتكون من 4 ركعات سرية."
    },
    {
        "id": 14,
        "q": "🧠 *سؤال دزايري:* \nشحال كاين من ركن في دين الإسلام؟",
        "opts": ["3 أركان", "4 أركان", "5 أركان", "6 أركان"],
        "ans": 2,
        "expl": "أركان الإسلام خمسة: الشهادتان، الصلاة، الزكاة، الصوم، وحج البيت."
    },
    {
        "id": 15,
        "q": "🧠 *سؤال دزايري:* \nشكون السورة اللي يستحب قراءتها كل نهار جمعة وتضوي بين الجمعتين؟",
        "opts": ["سورة الملك", "سورة يس", "سورة الكهف", "سورة الواقعة"],
        "ans": 2,
        "expl": "سورة الكهف تنور لصاحبها ما بين الجمعتين."
    },
    {
        "id": 16,
        "q": "🧠 *سؤال دزايري:* \nوين ولد النبي محمد عليه الصلاة والسلام؟",
        "opts": ["المدينة المنورة", "مكة المكرمة", "الطائف", "القدس الشريف"],
        "ans": 1,
        "expl": "ولد النبي ﷺ في مكة المكرمة عام الفيل."
    },
    {
        "id": 17,
        "q": "🧠 *سؤال دزايري:* \nشكون القارئ الجزائري الشهير بقراءة ورش عن نافع والمشهور في القنوات؟",
        "opts": ["الشيخ زكريا حمامة", "الشيخ ياسين الجزائري", "الشيخ سعيد دباح", "الشيخ منصور الوهراني"],
        "ans": 1,
        "expl": "الشيخ ياسين الجزائري معروف بتلاوته المتقنة برواية ورش عن نافع."
    },
    {
        "id": 18,
        "q": "🧠 *سؤال دزايري:* \nشحال من آية كاين في سورة الفاتحة؟",
        "opts": ["5 آيات", "6 آيات", "7 آيات", "8 آيات"],
        "ans": 2,
        "expl": "سورة الفاتحة متكونة من 7 آيات (السبع المثاني)."
    },
    {
        "id": 19,
        "q": "🧠 *سؤال دزايري:* \nشكون هي أطول سورة في المصحف الشريف كامل؟",
        "opts": ["سورة آل عمران", "سورة البقرة", "سورة النساء", "سورة المائدة"],
        "ans": 1,
        "expl": "سورة البقرة هي أطول سورة وتسمى سنام القرآن."
    },
    {
        "id": 20,
        "q": "🧠 *سؤال دزايري:* \nشهر رمضان المبارك شحال يقدر يكون عدد أيامه؟",
        "opts": ["28 يوم برك", "29 ولا 30 يوم", "31 يوم", "27 يوم ديما"],
        "ans": 1,
        "expl": "الأشهر الهجرية تكون إما 29 أو 30 يوم حسب هلال الشهر."
    },
    {
        "id": 21,
        "q": "🧠 *سؤال دزايري:* \nشكون الصحابي اللي كنيته \"أمير المؤمنين\" وكان معروف بالعدل وشدته في الحق؟",
        "opts": ["سيدنا أبو بكر", "سيدنا عمر بن الخطاب", "سيدنا عثمان", "سيدنا علي"],
        "ans": 1,
        "expl": "سيدنا عمر بن الخطاب رضي الله عنه هو الفاروق وأول من سمي بأمير المؤمنين."
    },
    {
        "id": 22,
        "q": "🧠 *سؤال دزايري:* \nشكون النبي اللي بلعو الحوت وقعد يسبح في بطنه؟",
        "opts": ["سيدنا يونس عليه السلام", "سيدنا يوسف", "سيدنا أيوب", "سيدنا نوح"],
        "ans": 0,
        "expl": "سيدنا يونس عليه السلام هو صاحب الحوت (ذو النون)."
    },
    {
        "id": 23,
        "q": "🧠 *سؤال دزايري:* \nشكون هي السورة اللي ما تبداش بالبسملة (بسم الله الرحمن الرحيم)؟",
        "opts": ["سورة الانفطار", "سورة التوبة", "سورة يونس", "سورة الكهف"],
        "ans": 1,
        "expl": "سورة التوبة (براءة) هي السورة الوحيدة في القرآن بدون بسملة."
    },
    {
        "id": 24,
        "q": "🧠 *سؤال دزايري:* \nشكون النبي اللي كلمو ربي سبحانه وتعالى مباشرة وتسمى \"كليم الله\"؟",
        "opts": ["سيدنا إبراهيم", "سيدنا عيسى", "سيدنا موسى عليه السلام", "سيدنا يوسف"],
        "ans": 2,
        "expl": "سيدنا موسى عليه السلام هو كليم الله."
    },
    {
        "id": 25,
        "q": "🧠 *سؤال دزايري:* \nشحال عدد أجزاء القرآن الكريم؟",
        "opts": ["20 جزء", "30 جزء", "40 جزء", "60 جزء"],
        "ans": 1,
        "expl": "القرآن الكريم مقسم لـ 30 جزء و60 حزب."
    },
    {
        "id": 26,
        "q": "🧠 *سؤال دزايري:* \nشكون الغزوة الأولى اللي تلاقاو فيها المسلمين مع الكفار وكانت الفتح الأعظم؟",
        "opts": ["غزوة أحد", "غزوة بدر الكبرى", "غزوة الخندق", "غزوة تبوك"],
        "ans": 1,
        "expl": "غزوة بدر الكبرى وقعت في 17 رمضان للسنة الثانية هجرية."
    },
    {
        "id": 27,
        "q": "🧠 *سؤال دزايري:* \nشكون الصحابي الجليل اللي تتلقب بـ \"ذو النورين\"؟",
        "opts": ["سيدنا عثمان بن عفان", "سيدنا علي بن أبي طالب", "سيدنا طلحة", "سيدنا الزبير"],
        "ans": 0,
        "expl": "سيدنا عثمان بن عفان رضي الله عنه لأنه تزوج ابنتي الرسول ﷺ (رقية وثم أم كلثوم)."
    },
    {
        "id": 28,
        "q": "🧠 *سؤال دزايري:* \nأينا سورة يعادل أجر قراءتها ثلث القرآن الكريم؟",
        "opts": ["سورة الفلق", "سورة الناس", "سورة الإخلاص", "سورة الكافرون"],
        "ans": 2,
        "expl": "سورة الإخلاص (قل هو الله أحد) تعدل ثلث القرآن."
    },
    {
        "id": 29,
        "q": "🧠 *سؤال دزايري:* \nشكون هي أقصر سورة في المصحف الشريف؟",
        "opts": ["سورة النصر", "سورة الكوثر", "سورة العصر", "سورة قريش"],
        "ans": 1,
        "expl": "سورة الكوثر تتكون من 3 آيات برك."
    },
    {
        "id": 30,
        "q": "🧠 *سؤال دزايري:* \nشكون السورة اللي المصرّح فيها بذكر اسم \"زيد\" الصحابي الجليل؟",
        "opts": ["سورة الأحزاب", "سورة الفتح", "سورة يس", "سورة النور"],
        "ans": 0,
        "expl": "زيد بن حارثة رضي الله عنه هو الصحابي الوحيد المذكور باسمه في سورة الأحزاب."
    }
]

QUIZ_BY_ID = {q["id"]: q for q in QUIZ_QUESTIONS}

# ══════════════════════════════════════════════════════════════════
#  حكم وأمثال جزائرية تربوية وإيمانية
# ══════════════════════════════════════════════════════════════════
ALGERIAN_PROVERBS = [
    "🇩🇿 *من الحكم الجزائرية:*\n«اللي دار الخير ما يندمش عليه، يلقاه عند ربي قداامو.»\n💡 *تذكير:* الصدقة والكلمة الطيبة والمساعدة دين مقضوض عند ربي سبحانه.",
    "🇩🇿 *من الحكم الجزائرية:*\n«مول النية يربح ومول الحيلة يخسر.»\n💡 *تذكير:* صفّي نيتك مع ربي والعباد، والله يجعل لك من كل ضيق مخرجاً.",
    "🇩🇿 *من الحكم الجزائرية:*\n«الصبر مفتاح الفرج، والشدة ما تدومش.»\n💡 *تذكير:* قال تعالى: ﴿إِنَّ مَعَ الْعُسْرِ يُسْرًا﴾، اصبر وأبشر بالخير.",
    "🇩🇿 *من الحكم الجزائرية:*\n«اللي فاتك بالحديث خليه يفوتك، واللي فاتك بالفعايل غير الحقو.»\n💡 *تذكير:* تنافسوا في الطاعات والعمل الصالح والخيرات.",
    "🇩🇿 *من الحكم الجزائرية:*\n«خالط العطار تنال عطرو، وخالط الحداد تنال جمرو.»\n💡 *تذكير:* قال النبي ﷺ: «مَثَلُ الجَلِيسِ الصَّالِحِ وَالسَّوْءِ كَحَامِلِ المِسْكِ وَنَافِخِ الكِيرِ».",
    "🇩🇿 *من الحكم الجزائرية:*\n«لسانك صوانك، إن صنته صانك وإن هنته هانك.»\n💡 *تذكير:* احفظ لسانك من الغيبة والنميمة يرحم والديك."
]

# ══════════════════════════════════════════════════════════════════
#  معلومات ومعارف قرآنية بالدارجة
# ══════════════════════════════════════════════════════════════════
QURAN_FACTS = [
    "💡 *معلومة قرآنية دزايرية:*\nهل تعلم بلي سورة *الملك* فيها 30 آية برك وتشفع لصاحبها في القبر حتى يغفر له ربي؟ حرص باش تقراها قبل ما ترقد كل ليلة!",
    "💡 *معلومة قرآنية دزايرية:*\nسورة *النمل* هي السورة الوحيدة في القرآن الكريم اللي فيها بسم الله الرحمن الرحيم مرتين (مرة في البدية ومرة في رسالة سيدنا سليمان لبلقيس).",
    "💡 *معلومة قرآنية دزايرية:*\nأطول آية في القرآن هي *آية الدين* في سورة البقرة (الآية 282)، وتتكلم على أحكام المعاملات المالية وكتابة الديون بوضوح شديد.",
    "💡 *معلومة قرآنية دزايرية:*\nسورة *المجادلة* هي السورة الوحيدة في المصحف اللي مذكور فيها لفظ الجلالة \"اللَّه\" في كل آية من آياتها بدون استثناء!",
    "💡 *معلومة قرآنية دزايرية:*\nسورة *الرحمن* تسمى \"عروس القرآن\"، وتكررت فيها آية ﴿فَبِأَيِّ آلَاءِ رَبِّكُمَا تُكَذِّبَانِ﴾ 31 مرة."
]

# ══════════════════════════════════════════════════════════════════
#  ألغاز وفوازير شعبية إسلامية بالدارجة
# ══════════════════════════════════════════════════════════════════
ALGERIAN_RIDDLES = [
    "🧩 *حجّيتك وما حجّيتك دزايرية:*\n«حاجة يمشي بلا رجلين وما يدخل غير للذان، وبلا بيه ما نعرفو وقت صلاتنا ولا أذاننا؟»\n\n📌 *الجواب:* الصّوت والنداء (الأذان).",
    "🧩 *حجّيتك وما حجّيتك دزايرية:*\n«شيء يبكي بلا عينين ويمشي بلا رجلين ويضوي للأمة كامل؟»\n\n📌 *الجواب:* الشمعة (أو العلم والتذكرة).",
    "🧩 *حجّيتك وما حجّيتك دزايرية:*\n«سورة في المصحف تسمات على اسم حشرة وربي ذكر فيها الخلية والشفاء للناس؟»\n\n📌 *الجواب:* سورة النحل."
]

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

# ── جلب قائمة السور من assabile AJAX ─────────────────────────────────────────
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
            name = SURAH_NAMES[sura_id - 1] if 1 <= sura_id <= 114 else f"سورة {sura_id}"
            rec_id = item.get("href", "#").lstrip("#")
            surahs.append({"sura_id": sura_id, "name": name, "rec_id": rec_id})
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
    "🏴⚔️ حضرموت":       (15.49, 49.12),
}

STATES_LIST = list(ALGERIA_STATES.keys())
STATES_PAGE_SIZE = 10

# ── لوحة المفاتيح الرئيسية المعدلة ───────────────────────────────────────────
MAIN_KEYBOARD = [
    [KeyboardButton("🕌 مواقيت الصلاة"), KeyboardButton("📖 تصفح القرآن الكريم")],
    [KeyboardButton("📍 أقرب مسجد / حلال / مقهى", request_location=True)],
    [KeyboardButton("🧠 مسابقة إسلامية"), KeyboardButton("💡 محتوى وثقافة")],
    [KeyboardButton("ℹ️ حول البوت")]
]

# ── المحتوى اليومي المتجدد بالدارجة الجزائرية ─────────────────────────────────
DAILY_CONTENT = {
    "azkar_sabah":   "☀️ *أذكار الصباح بالدارجة:*\nصباح الخير والبركة أخي/أختي! ما تنساش تبدا نهارك بذكر ربي:\n«أصبحنا وأصبح الملك لله والحمد لله، لا إله إلا الله وحده لا شريك له..»\nربي يحفظك ويوفقك في نهارك 🇩🇿",
    "azkar_massa":   "🌆 *أذكار المساء بالدارجة:*\nمساء الخير والأنوار! حصّن روحك وعائلتك بهذه الكلمات المباركة:\n«أمسينا وأمسى الملك لله والحمد لله.. أعوذ بكلمات الله التامات من شر ما خلق.»\nربي يمتعك بالصحة والعافية 🤲",
}

DAILY_PACKAGES = [
    (
        "🌟 *المحتوى اليومي المتجدد 🇩🇿*\n\n"
        "📖 *آية اليوم:* ﴿وَمَن يَتَّقِ اللَّهَ يَجْعَل لَّهُ مَخْرَجًا وَيَرْزُقْهُ مِنْ حَيْثُ لَا يَحْتَسِبُ﴾\n\n"
        "💬 *حديث اليوم:* قال النبي ﷺ: «تَبَسُّمُكَ فِي وَجْهِ أَخِيكَ صَدَقَةٌ»\n"
        "💡 *فكرة اليوم بالدارجة:* تبسّم في وجه خاوتك ووالديك اليوم، التبسم صدقة وما تكلفك والو وباهية عليك! 😊"
    ),
    (
        "🌟 *المحتوى اليومي المتجدد 🇩🇿*\n\n"
        "📖 *آية اليوم:* ﴿فَاذْكُرُونِي أَذْكُرْكُمْ وَاشْكُرُوا لِي وَلَا تَكْفُرُونِ﴾\n\n"
        "💬 *حديث اليوم:* قال رسول الله ﷺ: «الْكَلِمَةُ الطَّيِّبَةُ صَدَقَةٌ»\n"
        "💡 *فكرة اليوم بالدارجة:* هدرة حلوة وطيبة للي معاك في الدار ولا في الخدمة تقدر تفرح قلبه نهار كامل! ❤️"
    ),
    (
        "🌟 *المحتوى اليومي المتجدد 🇩🇿*\n\n"
        "📖 *آية اليوم:* ﴿وَقُل رَّبِّ زِدْنِي عِلْمًا﴾\n\n"
        "💬 *حديث اليوم:* قال رسول الله ﷺ: «مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ»\n"
        "💡 *فكرة اليوم بالدارجة:* اتعلم حجة جديدة اليوم في دينك ولا قرايتك، العلم يرفع مولاه في الداراوين!"
    )
]

DUA_SADAQA = (
    "🤲 *دعاء صدقة جارية*\n\n"
    "اللهم اجعل هذا البوت صدقةً جاريةً عن صاحبته *الأخت الأندلسية*،\n"
    "اللهم اغفر لها وارحمها وتقبّل منها،\n"
    "وبارك الله في ابنتها وجعلها قرةَ عينٍ لها ولوالدها المجاهد في أرض جزيرة محمد،\n"
    "اللهم احفظهم وانصرهم وثبّت أقدامهم. آمين 🇩🇿"
)

# ══════════════════════════════════════════════════════════════════
#  إرسال التحديث لمرة واحدة فقط لجميع المشتركين
# ══════════════════════════════════════════════════════════════════
UPDATE_MESSAGE_TEXT = (
    "واش خاوتنا! 👋\n\n"
    "حبين نخبّروكم بلي درنا *تحديثات وتغييرات جديدة* فالبوت باش تحسّن التجربة تاعكم وتخدموا بيه براحتكم. 🚀\n\n"
    "بعثنالكم هاد الميساج باش نتأكدوا بلي كلش راه يمشي عادي والاشتراك تاعكم ما راحش. إذا وصلك هاد الميساج، أسبابها بلي حسابك راه متصل 100%!\n\n"
    "صحيتوا على ثقتكم فينا، ونتمنى يعجبكم التحديث الجديد! ✨\n\n"
    "لا تنسونا من صالح دعائكم إخوانكم في الله المعتصم الوهراني والأخ خَطّاب الحضرمي."
)

async def send_update_broadcast(app):
    """إرسال رسالة التحديث مرة واحدة لكل إصدار — يتحقق من BROADCAST_VERSION."""
    stored_ver = db.get("broadcast_version", 0)
    if db.get("broadcast_sent") and stored_ver >= BROADCAST_VERSION:
        logger.info("رسالة التحديث أُرسلت مسبقاً لهذا الإصدار، لن تُعاد.")
        return

    all_users = (
        set(db["auto"]) | set(db["quiz"])
        | set(db["alarms"].keys()) | set(db["quiz_scores"].keys())
        | PROTECTED_IDS          # الأرقام المحمية تستقبل دائماً
    )
    logger.info(f"جاري إرسال رسالة التحديث v{BROADCAST_VERSION} لـ {len(all_users)} مشترك...")
    for chat_id in list(all_users):
        try:
            await app.bot.send_message(chat_id, UPDATE_MESSAGE_TEXT, parse_mode="Markdown")
            logger.info(f"✅ أُرسل لـ {chat_id}")
        except TelegramError as e:
            logger.warning(f"⚠️ فشل الإرسال لـ {chat_id}: {e}")
        await asyncio.sleep(0.08)

    db["broadcast_sent"]    = True
    db["broadcast_version"] = BROADCAST_VERSION
    save_db()
    logger.info("✅ انتهى إرسال التحديث.")

# ══════════════════════════════════════════════════════════════════
#  بداية البوت
# ══════════════════════════════════════════════════════════════════
def _register_user(user, chat_id: int):
    """يسجّل المستخدم تلقائياً بدون حذفه إذا كان مسجلاً سابقاً."""
    changed = False
    if chat_id not in db["auto"]:
        db["auto"].add(chat_id)
        changed = True
    if chat_id not in db["quiz"]:
        db["quiz"].add(chat_id)
        changed = True
    if chat_id not in db["quiz_scores"]:
        db["quiz_scores"][chat_id] = {
            "name":    (user.first_name or "مجهول")[:30],
            "correct": 0,
            "total":   0,
        }
        changed = True
    if changed:
        save_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    _register_user(user, chat_id)

    await update.message.reply_text(
        f"واش راك يا {user.first_name}؟ 👋\n"
        "مرحبا بيك في *البوت الإسلامي الدزايري* 🇩🇿\n\n"
        "✅ *رانا سجلناك تلقائياً في كامل خدمات البوت:*\n\n"
        "🕌 مواقيت الصلاة — *خيّر ولايتك* ويجيك تنبيه الأذان تلقائي ✅\n"
        "📖 تصفح القرآن واسمع بأصوات قراء دزايريين كبار\n"
        "📍 ابعث موقعك باش تعرف أقرب مسجد ومحل حلال ومقهى\n"
        "🧠 مسابقة إسلامية بالدارجة كل ساعتين — *مسجّل تلقائياً* ✅\n"
        "💡 محتوى وحكم وثقافة دزايرية متجددة يومياً\n"
        "🏆 قايمة الأوائل كل خميس في الليل — اللي يتصدّر يربح تكريم خاص 🎖\n"
        "☀️ أذكار الصباح والمساء والمحتوى اليومي — *تلقائي* ✅\n\n"
        "📌 *الأوامر المهمة:*\n"
        "• `/quiz` — شوف قائمة الأوائل في المسابقة\n"
        "• `/stop` — وقّف التنبيهات المؤقتة\n\n"
        "يرحم والديك 🤲 — بالصحة والراحة وحظ سعيد في المسابقات! 🏅",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════
#  مواقيت الصلاة
# ══════════════════════════════════════════════════════════════════
def get_prayer_times(lat: float, lon: float) -> dict | None:
    date_str = datetime.now().strftime("%d-%m-%Y")
    url = (
        f"https://api.aladhan.com/v1/timings/{date_str}"
        f"?latitude={lat}&longitude={lon}&method=21"
    )
    try:
        res = requests.get(url, timeout=10).json()
        return res["data"]["timings"] if res.get("code") == 200 else None
    except Exception:
        return None

PRAYER_NAMES = {
    "Fajr": "الفجر", "Dhuhr": "الظهر",
    "Asr": "العصر", "Maghrib": "المغرب", "Isha": "العشاء",
}

def _states_page_keyboard(page: int) -> InlineKeyboardMarkup:
    start  = page * STATES_PAGE_SIZE
    end    = start + STATES_PAGE_SIZE
    chunk  = STATES_LIST[start:end]
    total  = (len(STATES_LIST) + STATES_PAGE_SIZE - 1) // STATES_PAGE_SIZE

    rows = []
    for i in range(0, len(chunk), 2):
        row = []
        for state in chunk[i:i+2]:
            row.append(InlineKeyboardButton(state, callback_data=f"pray|{state}"))
        rows.append(row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"pray_page|{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total}", callback_data="noop"))
    if end < len(STATES_LIST):
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"pray_page|{page+1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)

async def prayer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *اختر ولايتك* لعرض مواقيت الصلاة وتفعيل تنبيه الأذان تلقائياً:",
        reply_markup=_states_page_keyboard(0),
        parse_mode="Markdown"
    )

async def prayer_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("|")[1])
    await query.edit_message_reply_markup(_states_page_keyboard(page))

async def prayer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    chat_id    = query.message.chat_id
    state_name = query.data.split("|", 1)[1]
    lat, lon   = ALGERIA_STATES[state_name]

    if db["alarms"].get(chat_id) != state_name:
        db["alarms"][chat_id] = state_name
        save_db()

    times = get_prayer_times(lat, lon)
    if times:
        text = (
            f"🕌 *مواقيت الصلاة — {state_name}*\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"🌅 الفجر:    {times['Fajr']}\n"
            f"☀️ الشروق:  {times['Sunrise']}\n"
            f"🕌 الظهر:    {times['Dhuhr']}\n"
            f"🌆 العصر:    {times['Asr']}\n"
            f"🌅 المغرب:   {times['Maghrib']}\n"
            f"🌃 العشاء:   {times['Isha']}\n\n"
            f"🔔 _تم تفعيل تنبيه الأذان لولايتك تلقائياً_ ✅"
        )
        back_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 العودة للولايات", callback_data="pray_page|0")
        ]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn)
    else:
        await query.edit_message_text("❌ الله غالب، ما قدرناش نجيبو المواقيت دُرك، عاود جرب من بعد.")

async def check_prayer_alarms(app):
    now_str = datetime.now().strftime("%H:%M")
    for chat_id, state in list(db["alarms"].items()):
        coords = ALGERIA_STATES.get(state, (36.75, 3.05))
        lat, lon = coords
        times = get_prayer_times(lat, lon)
        if times:
            for prayer_en, p_time in times.items():
                if prayer_en in PRAYER_NAMES and p_time == now_str:
                    prayer_ar = PRAYER_NAMES[prayer_en]
                    try:
                        await app.bot.send_message(
                            chat_id,
                            f"🕌 *حان وقت صلاة {prayer_ar}*\n"
                            f"📍 توقيت: {state}\n"
                            f"🕐 الساعة: {p_time}\n\n"
                            "تقبل الله منا ومنكم صالح الأعمال 🤲",
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
        await update.message.reply_text("❌ ما لقيناش هذه الولاية، ثبت في اسمها مليح.")

# ══════════════════════════════════════════════════════════════════
#  قسم القرآن الكريم — القراء الجزائريون
# ══════════════════════════════════════════════════════════════════
def reciters_keyboard(page: int) -> InlineKeyboardMarkup:
    start = page * RECITERS_PAGE_SIZE
    end   = start + RECITERS_PAGE_SIZE
    chunk = ALGERIAN_RECITERS[start:end]

    rows = []
    for r in chunk:
        rows.append([InlineKeyboardButton(
            f"🎙 {r['name']} ({r['riwaya']})",
            callback_data=f"reciter|{r['key']}|0"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"reciters_page|{page-1}"))
    total_pages = (len(ALGERIAN_RECITERS) + RECITERS_PAGE_SIZE - 1) // RECITERS_PAGE_SIZE
    if end < len(ALGERIAN_RECITERS):
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"reciters_page|{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(f"📄 الصفحة {page+1}/{total_pages}", callback_data="noop")])
    return InlineKeyboardMarkup(rows)

def surahs_keyboard(reciter_key: str, surahs: list, page: int) -> InlineKeyboardMarkup:
    start = page * SURAHS_PAGE_SIZE
    end   = start + SURAHS_PAGE_SIZE
    chunk = surahs[start:end]

    rows = []
    for i in range(0, len(chunk), 2):
        row = []
        for item in chunk[i:i+2]:
            sura_id = item["sura_id"]
            name    = item["name"]
            rec_id  = item.get("rec_id", "")
            cd      = f"surah|{reciter_key}|{sura_id}|{rec_id}"
            row.append(InlineKeyboardButton(f"{sura_id}. {name}", callback_data=cd))
        rows.append(row)

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
    key = reciter["key"]
    if key in db["surah_cache"]:
        return db["surah_cache"][key]

    if reciter["source"] == "assabile":
        surahs = fetch_assabile_surahs(reciter)
    elif reciter["source"] == "archive":
        surahs = [
            {"sura_id": n, "name": SURAH_NAMES[n-1], "rec_id": ""}
            for n in sorted(DABBAH_FILES.keys())
        ]
    else:
        surahs = [
            {"sura_id": n, "name": SURAH_NAMES[n-1], "rec_id": ""}
            for n in reciter["surahs"]
        ]

    db["surah_cache"][key] = surahs
    return surahs

async def quran_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *القرآن الكريم بأصوات قراء جزائريين 🇩🇿*\n\n"
        "اختر القارئ للاستماع إلى تلاواته العذبة:",
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
        f"⏳ اصبر شوية جارٍ تحميل قائمة السور بصوت {reciter['name']}...",
        parse_mode="Markdown"
    )

    surahs = get_reciter_surahs(reciter)
    if not surahs:
        await query.edit_message_text(
            f"❌ ما قدرناش نجيبو السور للشيخ {reciter['name']}. عاود جرب من بعد."
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

async def surah_audio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎵 رانا نجيبولك في الملف الصوتي...")
    parts = query.data.split("|")
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
            f"❌ مكاش رابط صوتي لسورة {surah_name} عند هذا القارئ حالياً."
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
            f"❌ تعذر إرسال الملف الصوتي مباشر لسورة {surah_name}.\n"
            f"تقدر تسمع ليها المباشر من هذا الرابط:\n{audio_url}"
        )

# ══════════════════════════════════════════════════════════════════
#  أقرب مسجد / حلال / مقهى
# ══════════════════════════════════════════════════════════════════
async def find_nearby_places(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude
    await update.message.reply_text("🔄 رانا نبحثولك على أقرب المساجد والمحلات والمقاهي القريبة منك...")
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
            return await update.message.reply_text("📍 للأسف ما لقينا حجة قريبة منك دُرك.")
        response_text = "📍 *النتائج القريبة منك:*\n\n"
        for idx, el in enumerate(elements, 1):
            tags     = el.get("tags", {})
            name     = tags.get("name", "بلاصة غير مسمات")
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
                f"📏 {dist:.2f} كم — 🔗 [افتح الخريطة]({map_link})\n\n"
            )
        await update.message.reply_text(
            response_text, parse_mode="Markdown", disable_web_page_preview=True
        )
    except Exception:
        await update.message.reply_text("❌ حدث خطأ أثناء الاتصال بالخرائط.")

# ══════════════════════════════════════════════════════════════════
#  الإرسال التلقائي والمحتوى اليومي
# ══════════════════════════════════════════════════════════════════
async def start_auto_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db["auto"].add(update.effective_chat.id)
    save_db()
    await update.message.reply_text("🕒 تم تفعيل الإرسال التلقائي بنجاح! رايح يلحقك كل جديد.")

async def stop_all_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # الأرقام المحمية لا تُوقَف أبداً
    if chat_id not in PROTECTED_IDS:
        db["alarms"].pop(chat_id, None)
        db["auto"].discard(chat_id)
        save_db()
        await update.message.reply_text("🔕 تم إيقاف كافة التنبيهات المؤقتة.")
    else:
        await update.message.reply_text("✅ حسابك محمي ومسجّل دائماً في البوت.")

async def send_sabah_content(app):
    for chat_id in list(db["auto"]):
        try:
            await app.bot.send_message(chat_id, DAILY_CONTENT["azkar_sabah"], parse_mode="Markdown")
        except Exception:
            pass

async def send_daily_package(app):
    selected_pkg = random.choice(DAILY_PACKAGES)
    for chat_id in list(db["auto"]):
        try:
            await app.bot.send_message(chat_id, selected_pkg, parse_mode="Markdown")
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
#  محتوى عشوائي للترفيه التفاعلي بالدارجة
# ══════════════════════════════════════════════════════════════════
async def send_random_culture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = random.choice(["higma", "quran", "riddle"])
    if category == "higma":
        msg = random.choice(ALGERIAN_PROVERBS)
    elif category == "quran":
        msg = random.choice(QURAN_FACTS)
    else:
        msg = random.choice(ALGERIAN_RIDDLES)
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════
#  المسابقة الإسلامية
# ══════════════════════════════════════════════════════════════════
def build_leaderboard_text() -> str:
    scores = db["quiz_scores"]
    if not scores:
        return "🏆 قايمة الأوائل ما زالت فارغة — جاوب على الأسئلة باش تطلع هنا!"

    ranked = sorted(scores.values(), key=lambda x: x["correct"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *ترتيب أوائل المسابقة الإسلامية الدزايرية* 🇩🇿\n"]
    for i, entry in enumerate(ranked[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        total = entry["total"] or 1
        pct   = int(entry["correct"] / total * 100)
        lines.append(
            f"{medal} *{entry['name']}* — {entry['correct']} إجابة صحيحة من {entry['total']} ({pct}%)"
        )
    return "\n".join(lines)

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_leaderboard_text()
    await update.message.reply_text(text, parse_mode="Markdown")

async def quiz_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_single_quiz(update.effective_chat.id, update.get_bot())

async def send_quiz(app):
    q = random.choice(QUIZ_QUESTIONS)
    markup = _quiz_keyboard(q)
    recipients = db["auto"] | db["quiz"]
    for chat_id in list(recipients):
        try:
            await app.bot.send_message(
                chat_id,
                q["q"] + "\n\n_خيّر الجواب الصحيح من تحت 👇_",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def send_single_quiz(chat_id: int, bot):
    q = random.choice(QUIZ_QUESTIONS)
    markup = _quiz_keyboard(q)
    try:
        await bot.send_message(
            chat_id,
            q["q"] + "\n\n_خيّر الجواب الصحيح من تحت 👇_",
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
    await query.answer()
    _, q_id_str, chosen_str = query.data.split("|")
    q = QUIZ_BY_ID.get(int(q_id_str))
    if not q:
        await query.message.reply_text("❌ السؤال هذا ما لقيناهش.")
        return
    chosen  = int(chosen_str)
    correct = q["ans"]
    chat_id = query.message.chat_id
    user    = query.from_user

    if chat_id not in db["quiz_scores"]:
        db["quiz_scores"][chat_id] = {
            "name":    (user.first_name or "مجهول")[:30],
            "correct": 0,
            "total":   0,
        }
    db["quiz_scores"][chat_id]["total"] += 1
    if chosen == correct:
        db["quiz_scores"][chat_id]["correct"] += 1
        verdict = "✅ *يعطيك الصحة! إجابتك صحيحة 100%* 🎉"
    else:
        verdict = (
            f"❌ *للأسف غلطت المره هذه!*\n"
            f"الجواب الصحيح هو: *{q['opts'][correct]}*"
        )
    save_db()

    result_text = (
        f"{q['q']}\n\n"
        f"{verdict}\n\n"
        f"💡 *الشرح بالدارجة:* {q['expl']}"
    )
    try:
        await query.message.edit_text(result_text, parse_mode="Markdown")
    except Exception:
        await query.message.reply_text(result_text, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════
#  منشورات الحداد والتضامن
# ══════════════════════════════════════════════════════════════════
MOURNING_START = date(2026, 7, 22)
MOURNING_DAYS  = 3

MOURNING_POSTS = [
    (
        "🇩🇿 *إنّا لله وإنّا إليه راجعون*\n\n"
        "﴿وَبَشِّرِ الصَّابِرِينَ ۝ الَّذِينَ إِذَا أَصَابَتْهُم مُّصِيبَةٌ قَالُوا إِنَّا لِلَّهِ وَإِنَّا إِلَيْهِ رَاجِعُونَ﴾\n\n"
        "قلوبنا كامل مع خاوتنا في الولايات المتضرّرة من حرائق الغابات… "
        "نشاركهم ألمهم ونحملو معاهم الهم.\n\n"
        "🤲 اللهم اجعل هذه النار برداً وسلاماً على أهلنا، "
        "وارحم شهداءنا، واشفِ جرحانا، وأعِد لهم ما فقدوه أضعافاً مضاعفة.\n\n"
        "🕯 *يوم الحداد الأول — رانا كامل معاكم يا أحرار الجزائر* 🇩🇿"
    ),
    (
        "🇩🇿 *تضامن ودعاء — حرائق الغابات الجزائرية*\n\n"
        "قال النبي ﷺ: «مَثَلُ المُؤمِنِينَ في تَوادِّهِم وتَراحُمِهِم وتَعاطُفِهِم، "
        "مَثَلُ الجَسَدِ، إذا اشتَكى مِنهُ عُضوٌ تَداعى له سائرُ الجَسَدِ بالسَّهَرِ والحُمَّى»\n\n"
        "أهلنا في الغابات يواجهون النار، ورانا معاهم بالدعاء والتضامن.\n\n"
        "🤲 اللهم أنزِل عليهم رحمتك، وكُن لهم عوناً وسنداً، وارزقهم الصبر والثبات.\n\n"
        "🕯 *يوم الحداد الثاني — الجزائر دائماً متحدة* 🇩🇿"
    ),
    (
        "🇩🇿 *دعاء الختام — ثالث أيام الحداد*\n\n"
        "«اللهم إنَّا نسألك بأسمائك الحسنى وصفاتك العُلا أن تُطفئ هذه النيران، "
        "وأن تُحيي ما أحرقته بنباتٍ وخير، "
        "وأن تشفي جرحانا وترحم شهداءنا وتُعوّض المتضرّرين.»\n\n"
        "ثلاثة أيام مرّت ونحن نحمل في قلوبنا جرح إخواننا… "
        "الجزائر لا تُكسر، وشعبها يتسامى دائماً بفضل الله.\n\n"
        "🕯 *وقفة وفاء لأرواح الشهداء* 🇩🇿"
    ),
]

async def send_mourning_post(app):
    today     = date.today()
    day_index = (today - MOURNING_START).days
    if day_index < 0 or day_index >= MOURNING_DAYS:
        return
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

    winner = ranked[0]
    lines.append(
        f"\n🎖 *يعطيك الصحة للمتصدّر {winner['name']}!* 🎉\n"
        "أنت الفائز الأكبر هذا الأسبوع معنا، بارك الله فيك ورزقك العلم النافع 🌟"
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
        "بوت إسلامي دزايري شامل يهدف لخدمة المسلمين بمواقيت الصلاة،\n"
        "تلاوات خاشعة بقراء دزايريين، مسابقات ثقافية وإسلامية بالدارجة،\n"
        "وأذكار وحكم شعبية متجددة يومياً.\n\n"
        "دعواتكم بالخير والرحمة لجميع القائمين عليه والمشتركين فيه! 🤲",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════
#  دالة البدء التشغيلية لمرّة واحدة عند بداية البوت
# ══════════════════════════════════════════════════════════════════
async def on_startup(app: Application):
    """تنفّذ تلقائياً عند بدء البوت."""
    ensure_protected_ids()          # ضمان الأرقام المحمية أولاً
    await send_update_broadcast(app)

# ══════════════════════════════════════════════════════════════════
#  نقطة الانطلاق
# ══════════════════════════════════════════════════════════════════
def main():
    if not TOKEN:
        raise RuntimeError("يرجى ضبط TELEGRAM_BOT_TOKEN في متغيرات البيئة")

    app = Application.builder().token(TOKEN).post_init(on_startup).build()

    # ── الجدولة ──────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Africa/Algiers")
    scheduler.add_job(check_prayer_alarms,     "interval", minutes=1,                              args=[app])
    scheduler.add_job(send_sabah_content,      CronTrigger(hour=6,  minute=0),                    args=[app])
    scheduler.add_job(send_daily_package,      CronTrigger(hour=8,  minute=0),                    args=[app])
    scheduler.add_job(send_massa_content,      CronTrigger(hour=17, minute=0),                    args=[app])
    scheduler.add_job(send_dua_sadaqa,         CronTrigger(hour=21, minute=0),                    args=[app])
    scheduler.add_job(send_quiz,               "interval", hours=2,                               args=[app])
    scheduler.add_job(send_weekly_leaderboard, CronTrigger(day_of_week="thu", hour=21, minute=0), args=[app])
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
    app.add_handler(MessageHandler(filters.Text(["💡 محتوى وثقافة"]),       send_random_culture))
    app.add_handler(MessageHandler(filters.Text(["ℹ️ حول البوت"]),            about_bot))
    app.add_handler(MessageHandler(filters.LOCATION,                           find_nearby_places))

    # ── الأزرار التفاعلية ─────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(prayer_page_callback,   pattern=r"^pray_page\|"))
    app.add_handler(CallbackQueryHandler(prayer_callback,        pattern=r"^pray\|"))
    app.add_handler(CallbackQueryHandler(reciters_page_callback, pattern=r"^reciters_page\|"))
    app.add_handler(CallbackQueryHandler(reciter_callback,       pattern=r"^reciter\|"))
    app.add_handler(CallbackQueryHandler(surahs_page_callback,   pattern=r"^surahs_page\|"))
    app.add_handler(CallbackQueryHandler(surah_audio_callback,   pattern=r"^surah\|"))
    app.add_handler(CallbackQueryHandler(quiz_answer_callback,   pattern=r"^quiz\|"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))

    app.run_polling()

if __name__ == "__main__":
    main()
