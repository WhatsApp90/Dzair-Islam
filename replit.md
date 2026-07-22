# البوت الإسلامي الدزايري

بوت تيليغرام إسلامي مخصص للجزائر، يوفر:
- مواقيت الصلاة لـ 48 ولاية جزائرية
- تصفح القرآن الكريم بأصوات قراء جزائريين
- البحث عن أقرب مسجد ومحل حلال ومقهى
- مسابقة إسلامية تلقائية
- أذكار الصباح والمساء والمحتوى اليومي

## Stack
- Python 3
- python-telegram-bot 21.9
- apscheduler 3.10.4
- requests 2.32.3

## Running
- التشغيل يتم على **Railway** (ليس على Replit)
- Replit يُستخدم فقط للتعديل على الكود ثم رفعه إلى GitHub
- متغير البيئة المطلوب: `TELEGRAM_BOT_TOKEN`

## Deployment
- الكود يُرفع إلى GitHub
- Railway يقرأ الكود من GitHub ويشغّله تلقائياً
- أمر التشغيل: `python bot.py` (كما في Procfile: `worker: python bot.py`)

## User preferences
- Replit is used for code editing only; deployment is on Railway
- After changes, push to GitHub (project is linked)
- No need to configure a run workflow on Replit
