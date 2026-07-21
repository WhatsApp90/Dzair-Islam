import os
import json
import logging
import random
from datetime import datetime, time as dt_time
import requests
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")

# ============================================================
# بيانات ولايات الجزائر مع إحداثياتها
# ============================================================
ALGERIA_WILAYAS = {
    "الجزائر العاصمة": (36.7538, 3.0588),
    "وهران": (35.6976, -0.6337),
    "قسنطينة": (36.3650, 6.6147),
    "عنابة": (36.9000, 7.7667),
    "سطيف": (36.1900, 5.4108),
    "باتنة": (35.5559, 6.1741),
    "بجاية": (36.7500, 5.0833),
    "تيزي وزو": (36.7167, 4.0500),
    "البليدة": (36.4700, 2.8333),
    "بسكرة": (34.8500, 5.7333),
    "تلمسان": (34.8783, -1.3150),
    "مستغانم": (35.9333, 0.0833),
    "ورقلة": (31.9500, 5.3333),
    "غرداية": (32.4833, 3.6833),
    "الأغواط": (33.8000, 2.8833),
    "تبسة": (35.4044, 8.1211),
    "جيجل": (36.5000, 5.7667),
    "سكيكدة": (36.8761, 6.9094),
    "سيدي بلعباس": (35.1878, -0.6308),
    "المدية": (36.2675, 2.7531),
    "ميلة": (36.4500, 6.2647),
    "عين الدفلى": (36.0333, 1.9667),
    "تيارت": (35.3700, 1.3170),
    "الشلف": (36.1647, 1.3333),
    "المسيلة": (35.8333, 4.4833),
    "سعيدة": (34.8333, 0.1500),
    "النعامة": (32.8333, -0.3167),
    "البيض": (33.6833, 0.1833),
    "أدرار": (27.8742, -0.2939),
    "تمنراست": (22.7853, 5.5228),
    "بشار": (31.6177, -2.2167),
    "تندوف": (27.6706, -8.1417),
    "إليزي": (28.0500, 8.0833),
    "بومرداس": (36.5000, 3.5833),
    "برج بوعريريج": (36.0667, 4.7667),
    "تيسمسيلت": (35.3167, 1.8333),
    "أم البواقي": (35.6500, 7.1167),
    "خنشلة": (35.4333, 7.1500),
    "سوق أهراس": (36.2833, 7.9500),
    "قالمة": (36.4500, 7.4333),
    "عين تموشنت": (35.3500, -1.0167),
    "الطارف": (36.7667, 8.2167),
    "معسكر": (35.4000, 0.1500),
    "غليزان": (35.7333, 0.5500),
}

# ============================================================
# الأذكار (تُرسل تلقائيا في أوقاتها دون أزرار)
# ============================================================
ADHKAR_SABAH = [
    "أصبحنا وأصبح الملك لله، والحمد لله، لا إله إلا الله وحده لا شريك له.",
    "اللهم بك أصبحنا وبك أمسينا، وبك نحيا وبك نموت وإليك النشور.",
    "اللهم أنت ربي لا إله إلا أنت، خلقتني وأنا عبدك، وأنا على عهدك ووعدك ما استطعت.",
    "سبحان الله وبحمده عدد خلقه ورضا نفسه وزنة عرشه ومداد كلماته.",
    "بسم الله الذي لا يضر مع اسمه شيء في الأرض ولا في السماء وهو السميع العليم.",
    "رضيت بالله ربا وبالإسلام دينا وبمحمد صلى الله عليه وسلم نبيا.",
]

ADHKAR_MASAA = [
    "أمسينا وأمسى الملك لله، والحمد لله، لا إله إلا الله وحده لا شريك له.",
    "اللهم بك أمسينا وبك أصبحنا، وبك نحيا وبك نموت وإليك المصير.",
    "أعوذ بكلمات الله التامات من شر ما خلق.",
    "اللهم إني أعوذ بك من الهم والحزن، والعجز والكسل، والبخل والجبن.",
    "بسم الله الذي لا يضر مع اسمه شيء في الأرض ولا في السماء وهو السميع العليم.",
]

# ============================================================
# القراء المتوفرون (التركيز على رواية ورش والقراء الجزائريين)
# ============================================================
QURAN_RECITERS = {
    "الشيخ عبد القادر البوشمالي (ورش - جزائري)": "https://server8.mp3quran.net/afs",
    "الشيخ محمود خليل الحصري (ورش)": "https://server8.mp3quran.net/afs",
    "الشيخ عبد الباسط عبد الصمد": "https://server8.mp3quran.net/afs",
    "الشيخ مشاري راشد العفاسي": "https://server8.mp3quran.net/afs",
    "الشيخ محمد صديق المنشاوي": "https://server8.mp3quran.net/afs",
    "الشيخ عبد الرحمن السديس": "https://server8.mp3quran.net/afs",
    "الشيخ سعود الشريم": "https://server8.mp3quran.net/afs",
    "الشيخ ماهر المعيقلي": "https://server8.mp3quran.net/afs",
}

# قائمة السور (رقم السورة: اسم السورة)
QURAN_SURAHS = [
    (1, "الفاتحة"), (2, "البقرة"), (3, "آل عمران"), (4, "النساء"), (5, "المائدة"),
    (6, "الأنعام"), (7, "الأعراف"), (8, "الأنفال"), (9, "التوبة"), (10, "يونس"),
    (11, "هود"), (12, "يوسف"), (13, "الرعد"), (14, "إبراهيم"), (15, "الحجر"),
    (16, "النحل"), (17, "الإسراء"), (18, "الكهف"), (19, "مريم"), (20, "طه"),
    (21, "الأنبياء"), (22, "الحج"), (23, "المؤمنون"), (24, "النور"), (25, "الفرقان"),
    (26, "الشعراء"), (27, "النمل"), (28, "القصص"), (29, "العنكبوت"), (30, "الروم"),
    (31, "لقمان"), (32, "السجدة"), (33, "الأحزاب"), (34, "سبأ"), (35, "فاطر"),
    (36, "يس"), (37, "الصافات"), (38, "ص"), (39, "الزمر"), (40, "غافر"),
    (41, "فصلت"), (42, "الشورى"), (43, "الزخرف"), (44, "الدخان"), (45, "الجاثية"),
    (46, "الأحقاف"), (47, "محمد"), (48, "الفتح"), (49, "الحجرات"), (50, "ق"),
    (51, "الذاريات"), (52, "الطور"), (53, "النجم"), (54, "القمر"), (55, "الرحمن"),
    (56, "الواقعة"), (57, "الحديد"), (58, "المجادلة"), (59, "الحشر"), (60, "الممتحنة"),
    (61, "الصف"), (62, "الجمعة"), (63, "المنافقون"), (64, "التغابن"), (65, "الطلاق"),
    (66, "التحريم"), (67, "الملك"), (68, "القلم"), (69, "الحاقة"), (70, "المعارج"),
    (71, "نوح"), (72, "الجن"), (73, "المزمل"), (74, "المدثر"), (75, "القيامة"),
    (76, "الإنسان"), (77, "المرسلات"), (78, "النبأ"), (79, "النازعات"), (80, "عبس"),
    (81, "التكوير"), (82, "الانفطار"), (83, "المطففين"), (84, "الانشقاق"), (85, "البروج"),
    (86, "الطارق"), (87, "الأعلى"), (88, "الغاشية"), (89, "الفجر"), (90, "البلد"),
    (91, "الشمس"), (92, "الليل"), (93, "الضحى"), (94, "الشرح"), (95, "التين"),
    (96, "العلق"), (97, "القدر"), (98, "البينة"), (99, "الزلزلة"), (100, "العاديات"),
    (101, "القارعة"), (102, "التكاثر"), (103, "العصر"), (104, "الهمزة"), (105, "الفيل"),
    (106, "قريش"), (107, "الماعون"), (108, "الكوثر"), (109, "الكافرون"), (110, "النصر"),
    (111, "المسد"), (112, "الإخلاص"), (113, "الفلق"), (114, "الناس"),
]

# ============================================================
# المحتوى اليومي: آية، حديث، حكمة
# ============================================================
DAILY_AYAT = [
    "﴿إِنَّ مَعَ الْعُسْرِ يُسْرًا﴾ [الشرح: 6]",
    "﴿وَمَنْ يَتَّقِ اللَّهَ يَجْعَلْ لَهُ مَخْرَجًا﴾ [الطلاق: 2]",
    "﴿وَقُلْ رَبِّ زِدْنِي عِلْمًا﴾ [طه: 114]",
    "﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾ [البقرة: 153]",
    "﴿وَأَقِيمُوا الصَّلَاةَ وَآتُوا الزَّكَاةَ﴾ [البقرة: 43]",
    "﴿وَمَنْ يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ﴾ [الطلاق: 3]",
    "﴿رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً﴾ [البقرة: 201]",
    "﴿الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ﴾ [الفاتحة: 2]",
    "﴿وَبَشِّرِ الصَّابِرِينَ﴾ [البقرة: 155]",
    "﴿إِنَّ الصَّلَاةَ كَانَتْ عَلَى الْمُؤْمِنِينَ كِتَابًا مَوْقُوتًا﴾ [النساء: 103]",
]

DAILY_HADITH = [
    "قال ﷺ: «إنما الأعمال بالنيات وإنما لكل امرئ ما نوى» [متفق عليه]",
    "قال ﷺ: «من حسن إسلام المرء تركه ما لا يعنيه» [رواه الترمذي]",
    "قال ﷺ: «المسلم من سلم المسلمون من لسانه ويده» [متفق عليه]",
    "قال ﷺ: «لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه» [متفق عليه]",
    "قال ﷺ: «الدين النصيحة» [رواه مسلم]",
    "قال ﷺ: «من كان يؤمن بالله واليوم الآخر فليقل خيرا أو ليصمت» [متفق عليه]",
    "قال ﷺ: «الطهور شطر الإيمان» [رواه مسلم]",
    "قال ﷺ: «تبسمك في وجه أخيك صدقة» [رواه الترمذي]",
    "قال ﷺ: «كلمتان خفيفتان على اللسان، ثقيلتان في الميزان: سبحان الله وبحمده، سبحان الله العظيم» [متفق عليه]",
    "قال ﷺ: «من سلك طريقا يلتمس فيه علما سهل الله له به طريقا إلى الجنة» [رواه مسلم]",
]

DAILY_HIKMA = [
    "من ترك شيئا لله عوضه الله خيرا منه.",
    "الصبر مفتاح الفرج.",
    "من جد وجد ومن زرع حصد.",
    "الكلمة الطيبة صدقة.",
    "الوقت كالسيف إن لم تقطعه قطعك.",
    "من لا يرحم الناس لا يرحمه الله.",
    "العلم نور والجهل ظلام.",
    "القناعة كنز لا يفنى.",
    "توكل على الله وخير فاعل.",
    "من جد وجد ومن سار على الدرب وصل.",
]

# ============================================================
# واجهة برمجة تطبيقات مواقيت الصلاة (Aladhan API)
# ============================================================
ALADHAN_API = "https://api.aladhan.com/v1/timings"

PRAYER_NAMES_AR = {
    "Fajr": "الفجر",
    "Sunrise": "الشروق",
    "Dhuhr": "الظهر",
    "Asr": "العصر",
    "Maghrib": "المغرب",
    "Isha": "العشاء",
}

def get_prayer_times(lat: float, lng: float) -> dict:
    """يجلب مواقيت الصلاة من Aladhan API."""
    try:
        resp = requests.get(
            ALADHAN_API,
            params={"latitude": lat, "longitude": lng, "method": 21},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        timings = data["data"]["timings"]
        return {PRAYER_NAMES_AR.get(k, k): v for k, v in timings.items() if k in PRAYER_NAMES_AR}
    except Exception as e:
        logger.error(f"خطأ في جلب المواقيت: {e}")
        return {}


def get_quran_audio_url(surah_num: int, reciter_url: str) -> str:
    """يبني رابط ملف صوتي للسورة من mp3quran."""
    return f"{reciter_url}/{str(surah_num).zfill(3)}.mp3"


def get_quran_text(surah_num: int) -> str:
    """يجلب نص السورة من AlQuran Cloud API."""
    try:
        resp = requests.get(
            f"https://api.alquran.cloud/v1/surah/{surah_num}/quran-uthmani",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        ayahs = data.get("ayahs", [])
        text = "\n".join(a["text"] for a in ayahs[:15])
        return f"سورة {data.get('name', '')} - {data.get('englishName', '')}\n\n{text}\n\n... (عرض أول 15 آية)"
    except Exception as e:
        logger.error(f"خطأ في جلب نص السورة: {e}")
        return "تعذر جلب النص حاليا."


def get_daily_content() -> str:
    """يختار آية وحديث وحكمة بناءً على يوم السنة."""
    day_of_year = datetime.now().timetuple().tm_yday
    ayah = DAILY_AYAT[day_of_year % len(DAILY_AYAT)]
    hadith = DAILY_HADITH[day_of_year % len(DAILY_HADITH)]
    hikma = DAILY_HIKMA[day_of_year % len(DAILY_HIKMA)]
    return (
        "🌙 محتوى يومي متجدد 🌙\n\n"
        f"📖 آية اليوم:\n{ayah}\n\n"
        f"📜 حديث اليوم:\n{hadith}\n\n"
        f"💡 حكمة اليوم:\n{hikma}"
    )


def find_nearby_mosques(lat: float, lng: float) -> list:
    """يبحث عن أقرب المساجد عبر Overpass API (OpenStreetMap)."""
    query = f"""
    [out:json];
    (
      node["amenity"="place_of_worship"]["religion"="muslim"](around:5000,{lat},{lng});
      way["amenity"="place_of_worship"]["religion"="muslim"](around:5000,{lat},{lng});
      node["amenity"="mosque"](around:5000,{lat},{lng});
      way["amenity"="mosque"](around:5000,{lat},{lng});
    );
    out center 10;
    """
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=25,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        results = []
        for el in elements[:8]:
            name = el.get("tags", {}).get("name", "مسجد")
            elat = el.get("lat", el.get("center", {}).get("lat", lat))
            elng = el.get("lon", el.get("center", {}).get("lon", lng))
            dist = geodesic((lat, lng), (elat, elng)).km
            results.append({"name": name, "lat": elat, "lng": elng, "dist": round(dist, 2)})
        results.sort(key=lambda x: x["dist"])
        return results[:5]
    except Exception as e:
        logger.error(f"خطأ في البحث عن المساجد: {e}")
        return []


def find_nearby_halal(lat: float, lng: float) -> list:
    """يبحث عن مطاعم حلال ومحلات ومقاهي قريبة."""
    query = f"""
    [out:json];
    (
      node["amenity"="restaurant"]["diet:halal"="yes"](around:5000,{lat},{lng});
      way["amenity"="restaurant"]["diet:halal"="yes"](around:5000,{lat},{lng});
      node["shop"="butcher"]["halal"="yes"](around:5000,{lat},{lng});
      way["shop"="butcher"]["halal"="yes"](around:5000,{lat},{lng});
      node["amenity"="cafe"](around:5000,{lat},{lng});
      way["amenity"="cafe"](around:5000,{lat},{lng});
    );
    out center 10;
    """
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=25,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        results = []
        for el in elements[:10]:
            tags = el.get("tags", {})
            name = tags.get("name", tags.get("name:ar", "محل"))
            kind = "مطعم حلال" if tags.get("amenity") == "restaurant" else (
                "جزّار حلال" if tags.get("shop") == "butcher" else "مقهى"
            )
            elat = el.get("lat", el.get("center", {}).get("lat", lat))
            elng = el.get("lon", el.get("center", {}).get("lon", lng))
            dist = geodesic((lat, lng), (elat, elng)).km
            results.append({"name": name, "kind": kind, "lat": elat, "lng": elng, "dist": round(dist, 2)})
        results.sort(key=lambda x: x["dist"])
        return results[:5]
    except Exception as e:
        logger.error(f"خطأ في البحث عن محلات الحلال: {e}")
        return []


# ============================================================
# واجهة المستخدم - لوحة المفاتيح الرئيسية
# (بدون زر الأذكار وبدون زر المحتوى اليومي)
# ============================================================
def main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["🕌 مواقيت الصلاة", "📖 تصفح القرآن الكريم"],
        ["📍 أقرب مسجد / حلال / مقهى", "ℹ️ حول البوت"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def wilaya_keyboard() -> InlineKeyboardMarkup:
    """لوحة اختيار الولاية (مقسّمة على صفوف)."""
    wilayas = sorted(ALGERIA_WILAYAS.keys())
    buttons = []
    for w in wilayas:
        buttons.append(InlineKeyboardButton(w, callback_data=f"wilaya:{w}"))
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)


def quran_reciters_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for name, url in QURAN_RECITERS.items():
        rows.append([InlineKeyboardButton(name, callback_data=f"reciter:{url}")])
    return InlineKeyboardMarkup(rows)


def surahs_keyboard() -> InlineKeyboardMarkup:
    """لوحة السور - مقسّمة على صفوف."""
    buttons = []
    for num, name in QURAN_SURAHS:
        buttons.append(InlineKeyboardButton(f"{num}. {name}", callback_data=f"surah:{num}"))
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    return InlineKeyboardMarkup(rows)


# ============================================================
# الأوامر
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "السلام عليكم ورحمة الله وبركاته 🌙\n\n"
        "أهلا بك في البوت الإسلامي الجزائري.\n"
        "اختر من القائمة ما تريد:\n\n"
        "🕌 مواقيت الصلاة - حسب ولايتك الجزائرية\n"
        "📖 تصفح القرآن الكريم - استماع ونص للسور\n"
        "📍 أقرب مسجد / حلال / مقهى - بناءً على موقعك\n\n"
        "🌙 المحتوى اليومي (آية + حديث + حكمة) والأذكار "
        "تُرسل تلقائيا في أوقاتها دون الحاجة لأي زر.",
        reply_markup=main_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "اختر أحد الأزرار في القائمة الرئيسية.\n"
        "للبحث الجغرافي أرسل موقعك (location).",
        reply_markup=main_keyboard(),
    )


# ============================================================
# معالج الرسائل النصية
# ============================================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == "🕌 مواقيت الصلاة":
        await update.message.reply_text(
            "اختر ولايتك الجزائرية لعرض مواقيت الصلاة:",
            reply_markup=wilaya_keyboard(),
        )
    elif text == "📖 تصفح القرآن الكريم":
        await update.message.reply_text(
            "اختر القارئ أولا:", reply_markup=quran_reciters_keyboard()
        )
    elif text == "📍 أقرب مسجد / حلال / مقهى":
        await update.message.reply_text(
            "📍 أرسل موقعك (Location) عبر زر الموقع في تيليجرام "
            "لأبحث عن أقرب مسجد ومحلات حلال ومقاهي قريبة منك.\n\n"
            "أو اختر ولايتك:",
            reply_markup=wilaya_keyboard(),
        )
    elif text == "ℹ️ حول البوت":
        await update.message.reply_text(
            "البوت الإسلامي الجزائري 🇩🇿\n\n"
            "مواقيت الصلاة لكل ولايات الجزائر\n"
            "القرآن الكريم كامل بأصوات أشهر القراء\n"
            "البحث عن المساجد ومحلات الحلال والمقاهي\n"
            "محتوى يومي وأذكار تُرسل تلقائيا في أوقاتها\n\n"
            "نسأل الله الإخلاص والقبول."
        )
    else:
        await update.message.reply_text(
            "اختر من القائمة:", reply_markup=main_keyboard()
        )


# ============================================================
# معالج الموقع الجغرافي
# ============================================================
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    loc = update.message.location
    if not loc:
        await update.message.reply_text("تعذر قراءة الموقع.")
        return
    lat, lng = loc.latitude, loc.longitude
    await update.message.reply_text("🔍 جاري البحث عن أقرب مسجد ومحلات حلال ومقاهي...")

    mosques = find_nearby_mosques(lat, lng)
    halal = find_nearby_halal(lat, lng)

    msg = "🕌 أقرب المساجد:\n"
    if mosques:
        for m in mosques:
            maps_url = f"https://www.openstreetmap.org/?mlat={m['lat']}&mlon={m['lng']}&zoom=17"
            msg += f"\n• {m['name']} ({m['dist']} كم)\n  📍 {maps_url}"
    else:
        msg += "لم يتم العثور على مساجد قريبة."

    msg += "\n\n🥩 محلات الحلال والمقاهي:\n"
    if halal:
        for h in halal:
            maps_url = f"https://www.openstreetmap.org/?mlat={h['lat']}&mlon={h['lng']}&zoom=17"
            msg += f"\n• {h['name']} - {h['kind']} ({h['dist']} كم)\n  📍 {maps_url}"
    else:
        msg += "لم يتم العثور على محلات قريبة."

    await update.message.reply_text(msg, disable_web_page_preview=True)


# ============================================================
# معالج أزرار الرد (Callback)
# ============================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # اختيار الولاية
    if data.startswith("wilaya:"):
        wilaya = data.split(":", 1)[1]
        coords = ALGERIA_WILAYAS.get(wilaya)
        if not coords:
            await query.message.reply_text("تعذر العثور على الولاية.")
            return
        lat, lng = coords
        await query.message.reply_text(f"🕌 مواقيت الصلاة - {wilaya}\nجاري الجلب...")
        timings = get_prayer_times(lat, lng)
        if not timings:
            await query.message.reply_text("تعذر جلب المواقيت الآن. حاول لاحقا.")
            return
        msg = f"🕌 مواقيت الصلاة - {wilaya}\n\n"
        for name, time in timings.items():
            msg += f"• {name}: {time}\n"
        msg += "\n✅ تم الجلب من Aladhan API (طريقة 21 - الجزائر)"
        await query.message.reply_text(msg)

    # اختيار القارئ
    elif data.startswith("reciter:"):
        reciter_url = data.split(":", 1)[1]
        context.user_data["reciter_url"] = reciter_url
        await query.message.reply_text(
            "اختر السورة التي تريد الاستماع إليها:",
            reply_markup=surahs_keyboard(),
        )

    # اختيار السورة
    elif data.startswith("surah:"):
        surah_num = int(data.split(":", 1)[1])
        reciter_url = context.user_data.get("reciter_url", "https://server8.mp3quran.net/afs")
        surah_name = next((n for num, n in QURAN_SURAHS if num == surah_num), "")
        audio_url = get_quran_audio_url(surah_num, reciter_url)
        text = get_quran_text(surah_num)
        msg = f"📖 سورة {surah_name}\n\n{text}\n\n🎧 استماع:\n{audio_url}"
        await quer
