import os
import logging
import asyncio
import requests
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# جلب التوكن من متغيرات البيئة في Railway
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

db = {"alarms": {}, "auto": set()} 

ALGERIA_STATES = {
    "1- أدرار": (27.87, -0.29), "2- الشلف": (36.16, 1.33), "16- الجزائر": (36.75, 3.05),
    "19- سطيف": (36.19, 5.41), "31- وهران": (35.69, -0.63),
}

MAIN_KEYBOARD = [
    [KeyboardButton("🕌 مواقيت الصلاة"), KeyboardButton("📖 تصفح القرآن الكريم")],
    [KeyboardButton("📍 أقرب مسجد / حلال / مقهى", request_location=True)],
    [KeyboardButton("ℹ️ حول البوت")]
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً بك في البوت الإسلامي الجزائري.\n\n"
        "💡 الميزات المتاحة:\n"
        "• 🕌 مواقيت الصلاة لـ 48 ولاية.\n"
        "• 📢 تفعيل الأذان التلقائي عبر الأمر: `/alarm اسم_الولاية`\n"
        "• 📖 تصفح القرآن والاستماع (رواية ورش وقراء جزائريين).\n"
        "• 📍 إرسال الموقع لمعرفة أقرب مسجد ومحل ومقهى.\n"
        "• 🕒 تفعيل الإرسال التلقائي للأذكار والمحتوى اليومي عبر الأمر: `/auto`",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
        parse_mode="Markdown"
    )

async def get_prayer_times(lat, lon):
    url = f"https://aladhan.com{datetime.now().strftime('%d-%m-%Y')}?latitude={lat}&longitude={lon}&method=21"
    try:
        res = requests.get(url).json()
        return res['data']['timings'] if res.get('code') == 200 else None
    except: return None

async def prayer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(state, callback_data=f"pray_{state}")] for state in ALGERIA_STATES.keys()]
    await update.message.reply_text("📌 اختر ولايتك لعرض مواقيت الصلاة الحالية:", reply_markup=InlineKeyboardMarkup(keyboard))

async def prayer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    state_name = query.data.split("_")[1]
    lat, lon = ALGERIA_STATES[state_name]
    times = await get_prayer_times(lat, lon)
    if times:
        text = f"🕌 مواقيت الصلاة في ولاية ({state_name}) ليوم {datetime.now().strftime('%Y-%m-%d')}:\n\n" \
               f"🌅 الفجر: {times['Fajr']}\n☀️ الشروق: {times['Sunrise']}\n" \
               f"🕌 الظهر: {times['Dhuhr']}\n🌆 العصر: {times['Asr']}\n" \
               f"🌅 المغرب: {times['Maghrib']}\n🌃 العشاء: {times['Isha']}"
        await query.edit_message_text(text)
    else:
        await query.edit_message_text("❌ عذراً، تعذر جلب المواقيت حالياً.")

async def check_prayer_alarms(context: ContextTypes.DEFAULT_TYPE):
    now_str = datetime.now().strftime("%H:%M")
    for chat_id, state in list(db["alarms"].items()):
        lat, lon = ALGERIA_STATES.get(state, (36.75, 3.05))
        times = await get_prayer_times(lat, lon)
        if times:
            for prayer, p_time in times.items():
                if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'] and p_time == now_str:
                    try: await context.bot.send_message(chat_id, f"🕌 حان الآن موعد آذان صلاة {prayer} حسب توقيت ولاية {state} 🇩🇿")
                    except: pass

async def set_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = " ".join(context.args)
    if not state:
        return await update.message.reply_text("⚠️ يرجى كتابة اسم الولاية بعد الأمر. مثال:\n`/alarm 16- الجزائر`", parse_mode="Markdown")
    matched_state = next((s for s in ALGERIA_STATES if state in s), None)
    if matched_state:
        db["alarms"][update.effective_chat.id] = matched_state
        await update.message.reply_text(f"🔔 تم تفعيل تنبيهات الأذان التلقائي لولاية: {matched_state}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الولاية. يرجى كتابتها بشكل صحيح.")

RECITERS = {
    "1": ("الدوكالي محمد العالم (ورش)", "Libyan_Al_Doukali_Muhammad_Al_Alim_128kbps"),
    "2": ("ياسين الجزائري (ورش)", "Yassine_Al_Djazairi_64kbps"),
    "3": ("رياض الجزائري (ورش)", "Riad_Ait_Hama_128kbps"),
    "4": ("عبد الباسط عبد الصمد", "Abdul_Basit_Abdul_Samad_128kbps"),
    "5": ("ماهر المعيقلي", "MaherMuaiqly128kbps"),
}

async def quran_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📖 تصفح القرآن الكريم.\nللوصول السريع إلى أي سورة، أرسل رقمها من (1 إلى 114):\nمثال: أرسل الرقم `1` لعرض سورة الفاتحة."
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_quran_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit() and 1 <= int(text) <= 114:
        sura_num = int(text)
        res = requests.get(f"https://alquran.cloud{sura_num}").json()
        if res.get("code") == 200:
            sura_data = res["data"]
            ayyahs = "\n".join([f"﴿{ay['numberInSurah']}﴾ {ay['text']}" for ay in sura_data["ayyahs"]])
            keyboard = [[InlineKeyboardButton(f"🔊 {v[0]}", callback_data=f"listen_{sura_num}_{k}")] for k, v in RECITERS.items()]
            full_text = f"📖 *سورة {sura_data['name']}* ({sura_data['englishName']})\n\n{ayyahs}"
            if len(full_text) > 4000:
                await update.message.reply_text(full_text[:4000], parse_mode="Markdown")
                await update.message.reply_text(full_text[4000:], reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text(full_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def listen_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, sura, reciter_id = query.data.split("_")
    reciter_name, reciter_identifier = RECITERS[reciter_id]
    audio_url = f"https://islamic.network{reciter_identifier}/{sura}.mp3"
    await query.message.reply_audio(audio=audio_url, title=f"سورة رقم {sura}", performer=reciter_name)

async def find_nearby_places(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude
    await update.message.reply_text("🔄 جاري البحث عن أقرب المساجد والمحلات الحلال والمقاهي المحيطة بك...")
    query = f"""
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
        res = requests.post("https://overpass-api.de", data={"data": query}).json()
        elements = res.get("elements", [])
        if not elements: return await update.message.reply_text("📍 لم نتمكن من العثور على مرافق قريبة في هذا النطاق.")
        response_text = "📍 *النتائج القريبة منك (تفتح مباشرة على الخريطة):*\n\n"
        for idx, el in enumerate(elements, 1):
            tags = el.get("tags", {})
            name = tags.get("name", "مرفق غير مسمى")
            amenity = tags.get("amenity", tags.get("shop", "محل تجاري"))
            icon = "🕌" if amenity == "place_of_worship" else ("☕" if amenity == "cafe" else "🥩")
            p_lat, p_lon = el["lat"], el["lon"]
            map_link = f"https://google.com{p_lat},{p_lon}"
            from math import radians, cos, sin, asin, sqrt
            lon1, lat1, lon2, lat2 = map(radians, [lon, lat, p_lon, p_lat])
            dist = 2 * 6371 * asin(sqrt(sin((lat2 - lat1)/2)**2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1)/2)**2))
            response_text += f"{idx}. {icon} *{name}*\n📏 المسافة: {dist:.2f} كم\n🔗 [رابط الخريطة]({map_link})\n\n"
        await update.message.reply_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
    except: await update.message.reply_text("❌ حدث خطأ أثناء الاتصال بخدمة الخرائط.")

DAILY_CONTENT = {
    "azkar_sabah": "☀️ *أذكار الصباح:*\nأصبحنا وأصبح الملك لله والحمد لله..",
    "azkar_massa": "🌆 *أذكار المساء:*\nأمسينا وأمسي الملك لله والحمد لله..",
    "daily_package": "🌟 *المحتوى اليومي المتجدد:*\n\n📖 *آية:* {۞ وَمَن يَتَّقِ اللَّهَ يَجْعَل لَّهُ مَخْرَجًا}"
}

async def start_auto_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db["auto"].add(update.effective_chat.id)
    await update.message.reply_text("🕒 تم تفعيل الإرسال التلقائي بنجاح!")

async def stop_all_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db["alarms"].pop(chat_id, None)
    db["auto"].discard(chat_id)
    await update.message.reply_text("🔕 تم إيقاف كافة التنبيهات.")

async def send_sabah_content(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in db["auto"]:
        try: await context.bot.send_message(chat_id, DAILY_CONTENT["azkar_sabah"], parse_mode="Markdown")
        except: pass

async def send_daily_package(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in db["auto"]:
        try: await context.bot.send_message(chat_id, DAILY_CONTENT["daily_package"], parse_mode="Markdown")
        except: pass

async def send_massa_content(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in db["auto"]:
        try: await context.bot.send_message(chat_id, DAILY_CONTENT["azkar_massa"], parse_mode="Markdown")
        except: pass

async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ *حول البوت الإسلامي الجزائري* 🇩🇿\n\nبوت متكامل لخدمتك.", parse_mode="Markdown")

def main():
    if not TOKEN:
        raise RuntimeError("يرجى ضبط الـ TELEGRAM_BOT_TOKEN في متغيرات البيئة")
    
    app = Application.builder().token(TOKEN).build()
    scheduler = AsyncIOScheduler(timezone="Africa/Algiers")
    
    scheduler.add_job(check_prayer_alarms, 'interval', minutes=1, args=[app])
    scheduler.add_job(send_sabah_content, CronTrigger(hour=6, minute=0), args=[app])
    scheduler.add_job(send_daily_package, CronTrigger(hour=8, minute=0), args=[app])
    scheduler.add_job(send_massa_content, CronTrigger(hour=17, minute=0), args=[app])
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alarm", set_alarm))
    app.add_handler(CommandHandler("auto", start_auto_broadcast))
    app.add_handler(CommandHandler("stop", stop_all_services))
    
    app.add_handler(MessageHandler(filters.Text("🕌 مواقيت الصلاة"), prayer_menu))
    app.add_handler(MessageHandler(filters.Text("📖 تصفح القرآن الكريم"), quran_menu))
    app.add_handler(filters.LOCATION, find_nearby_places)
    app.add_handler(MessageHandler(filters.Text("ℹ️ حول البوت"), about_bot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quran_request))
    
    app.add_handler(CallbackQueryHandler(prayer_callback, pattern="^pray_"))
    app.add_handler(CallbackQueryHandler(listen_callback, pattern="^listen_"))

    app.run_polling()

if __name__ == "__main__":
    main()
