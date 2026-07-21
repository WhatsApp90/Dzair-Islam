import os
import logging
import requests
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

# ── قاعدة بيانات مؤقتة ──────────────────────────────────────────────────────
db = {"alarms": {}, "auto": set()}

# ── الولايات الـ 48 ──────────────────────────────────────────────────────────
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
    [KeyboardButton("ℹ️ حول البوت")]
]

# ── القراء ──────────────────────────────────────────────────────────────────
RECITERS = {
    "1": ("الدوكالي محمد العالم (ورش)",  "Libyan_Al_Doukali_Muhammad_Al_Alim_128kbps"),
    "2": ("ياسين الجزائري (ورش)",         "Yassine_Al_Djazairi_64kbps"),
    "3": ("رياض الجزائري (ورش)",          "Riad_Ait_Hama_128kbps"),
    "4": ("عبد الباسط عبد الصمد",         "Abdul_Basit_Abdul_Samad_128kbps"),
    "5": ("ماهر المعيقلي",                "MaherMuaiqly128kbps"),
}

# ── المحتوى اليومي ───────────────────────────────────────────────────────────
DAILY_CONTENT = {
    "azkar_sabah":  "☀️ *أذكار الصباح:*\nأصبحنا وأصبح الملك لله والحمد لله..",
    "azkar_massa":  "🌆 *أذكار المساء:*\nأمسينا وأمسي الملك لله والحمد لله..",
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
#  مواقيت الصلاة
# ══════════════════════════════════════════════════════════════════

def get_prayer_times(lat: float, lon: float) -> dict | None:
    """جلب مواقيت الصلاة من aladhan.com (مزامن — يُستدعى خارج async)."""
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
    """تحقق من مواقيت الأذان وأرسل تنبيهاً عند الموعد."""
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
    matched_state = next((s for s in ALGERIA_STATES if state in s), None)
    if matched_state:
        db["alarms"][update.effective_chat.id] = matched_state
        await update.message.reply_text(f"🔔 تم تفعيل تنبيهات الأذان لولاية: {matched_state}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الولاية. يرجى كتابتها بشكل صحيح.")


# ══════════════════════════════════════════════════════════════════
#  القرآن الكريم
# ══════════════════════════════════════════════════════════════════

async def quran_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 تصفح القرآن الكريم.\n"
        "أرسل رقم السورة من (1 إلى 114):\n"
        "مثال: أرسل `1` لعرض سورة الفاتحة.",
        parse_mode="Markdown"
    )


async def handle_quran_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit() and 1 <= int(text) <= 114:
        sura_num = int(text)
        try:
            res = requests.get(
                f"https://api.alquran.cloud/v1/surah/{sura_num}",
                timeout=10
            ).json()
        except Exception:
            return await update.message.reply_text("❌ تعذر الاتصال بخادم القرآن.")

        if res.get("code") == 200:
            sura_data = res["data"]
            ayyahs = "\n".join(
                f"﴿{ay['numberInSurah']}﴾ {ay['text']}"
                for ay in sura_data["ayahs"]
            )
            keyboard = [
                [InlineKeyboardButton(f"🔊 {v[0]}", callback_data=f"listen|{sura_num}|{k}")]
                for k, v in RECITERS.items()
            ]
            full_text = (
                f"📖 *سورة {sura_data['name']}* ({sura_data['englishName']})\n\n"
                f"{ayyahs}"
            )
            if len(full_text) > 4000:
                await update.message.reply_text(full_text[:4000], parse_mode="Markdown")
                await update.message.reply_text(
                    full_text[4000:],
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    full_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text("❌ لم يتم العثور على السورة.")


async def listen_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, sura, reciter_id = query.data.split("|")
    reciter_name, reciter_identifier = RECITERS[reciter_id]
    audio_url = (
        f"https://cdn.islamic.network/quran/audio-surah/128/"
        f"{reciter_identifier}/{sura}.mp3"
    )
    await query.message.reply_audio(
        audio=audio_url,
        title=f"سورة رقم {sura}",
        performer=reciter_name
    )


# ══════════════════════════════════════════════════════════════════
#  أقرب مسجد / حلال / مقهى
# ══════════════════════════════════════════════════════════════════

async def find_nearby_places(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude
    await update.message.reply_text(
        "🔄 جاري البحث عن أقرب المساجد والمحلات الحلال والمقاهي..."
    )
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
            data={"data": overpass_query},
            timeout=30
        ).json()
        elements = res.get("elements", [])
        if not elements:
            return await update.message.reply_text(
                "📍 لم نتمكن من العثور على مرافق قريبة في هذا النطاق."
            )
        response_text = "📍 *النتائج القريبة منك (تفتح مباشرة على الخريطة):*\n\n"
        for idx, el in enumerate(elements, 1):
            tags = el.get("tags", {})
            name = tags.get("name", "مرفق غير مسمى")
            amenity = tags.get("amenity", tags.get("shop", "محل تجاري"))
            icon = "🕌" if amenity == "place_of_worship" else ("☕" if amenity == "cafe" else "🥩")
            p_lat, p_lon = el["lat"], el["lon"]
            map_link = f"https://www.google.com/maps?q={p_lat},{p_lon}"
            lon1, lat1, lon2, lat2 = map(radians, [lon, lat, p_lon, p_lat])
            dist = 2 * 6371 * asin(
                sqrt(sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2)
            )
            response_text += (
                f"{idx}. {icon} *{name}*\n"
                f"📏 المسافة: {dist:.2f} كم\n"
                f"🔗 [رابط الخريطة]({map_link})\n\n"
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
    await update.message.reply_text("🕒 تم تفعيل الإرسال التلقائي بنجاح!")


async def stop_all_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db["alarms"].pop(chat_id, None)
    db["auto"].discard(chat_id)
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
#  معلومات البوت
# ══════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً بك في البوت الإسلامي الجزائري.\n\n"
        "💡 الميزات المتاحة:\n"
        "• 🕌 مواقيت الصلاة لـ 48 ولاية جزائرية.\n"
        "• 📢 تفعيل الأذان التلقائي: `/alarm اسم_الولاية`\n"
        "• 📖 تصفح القرآن والاستماع (ورش وقراء جزائريون).\n"
        "• 📍 إرسال موقعك لمعرفة أقرب مسجد ومحل ومقهى.\n"
        "• 🕒 إرسال تلقائي للأذكار والمحتوى اليومي: `/auto`\n"
        "• 🔕 إيقاف جميع التنبيهات: `/stop`",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
        parse_mode="Markdown"
    )


async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *حول البوت الإسلامي الجزائري* 🇩🇿\n\n"
        "بوت متكامل يخدم المسلمين الجزائريين بمواقيت الصلاة والقرآن والأذكار اليومية.",
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
    scheduler.add_job(check_prayer_alarms,  "interval", minutes=1,                    args=[app])
    scheduler.add_job(send_sabah_content,   CronTrigger(hour=6,  minute=0),           args=[app])
    scheduler.add_job(send_daily_package,   CronTrigger(hour=8,  minute=0),           args=[app])
    scheduler.add_job(send_massa_content,   CronTrigger(hour=17, minute=0),           args=[app])
    scheduler.add_job(send_dua_sadaqa,      CronTrigger(hour=21, minute=0),           args=[app])
    scheduler.start()

    # ── الأوامر ───────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alarm", set_alarm))
    app.add_handler(CommandHandler("auto",  start_auto_broadcast))
    app.add_handler(CommandHandler("stop",  stop_all_services))

    # ── الرسائل النصية ────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.Text(["🕌 مواقيت الصلاة"]),   prayer_menu))
    app.add_handler(MessageHandler(filters.Text(["📖 تصفح القرآن الكريم"]), quran_menu))
    app.add_handler(MessageHandler(filters.Text(["ℹ️ حول البوت"]),        about_bot))
    app.add_handler(MessageHandler(filters.LOCATION,                       find_nearby_places))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,        handle_quran_request))

    # ── الأزرار التفاعلية ─────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(prayer_callback, pattern=r"^pray\|"))
    app.add_handler(CallbackQueryHandler(listen_callback, pattern=r"^listen\|"))

    app.run_polling()


if __name__ == "__main__":
    main()
