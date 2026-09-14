import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- ۱. تنظیمات لاگ‌ها (برای دیدن بهتر خطاها در Render) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- ۲. خواندن متغیرهای محیطی از Render ---
# توکن ربات (در تنظیمات Render باید تعریف شود)
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# آدرس عمومی سرویس در Render (Render به صورت خودکار این را به برنامه می‌دهد)
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

# پورت (Render به صورت خودکار اختصاص می‌دهد، در غیر این صورت ۱۰۰۰۰)
PORT = int(os.environ.get("PORT", 10000))

# مسیر دریافت آپدیت‌ها
WEBHOOK_PATH = "/webhook"
# آدرس کامل وب‌هوک
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

if not BOT_TOKEN:
    raise ValueError("❌ خطای بحرانی: متغیر محیطی TELEGRAM_TOKEN در Render تنظیم نشده است!")

# --- ۳. مقداردهی اولیه ربات و دیسپچر ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- ۴. هندلرهای ربات (دستورات) ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """پاسخ به دستور /start"""
    await message.answer("سلام! ربات با موفقیت روی Render راه‌اندازی شد. 🚀")

# --- ۵. تسک پس‌زمینه (حلقه تحلیل شما) ---
async def analysis_loop():
    """این تابع در پس‌زمینه اجرا می‌شود و ربات را متوقف نمی‌کند"""
    logger.info("🔄 تسک پس‌زمینه تحلیل شروع به کار کرد.")
    while True:
        try:
            # ⬇️ کدهای تحلیل خود را اینجا بنویسید ⬇️
            # مثلاً: await check_markets()
            logger.info("در حال انجام تحلیل دوره‌ای...")
            
            # هر ۶۰ ثانیه یکبار اجرا شود (زمان را می‌توانید تغییر دهید)
            await asyncio.sleep(60) 
        except asyncio.CancelledError:
            logger.info("تسک پس‌زمینه متوقف شد.")
            break
        except Exception as e:
            logger.error(f"خطا در تسک پس‌زمینه: {e}")
            await asyncio.sleep(10)

# --- ۶. رویدادهای Startup و Shutdown (مدیریت وب‌هوک) ---
async def on_startup(bot: Bot):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logger.info(f"✅ وب‌هوک با موفقیت روی آدرس {WEBHOOK_URL} تنظیم شد.")
    else:
        logger.warning("⚠️ هشدار: RENDER_EXTERNAL_URL تنظیم نشده است. وب‌هوک تنظیم نشد.")

async def on_shutdown(bot: Bot):
    logger.info("🛑 در حال خاموش کردن ربات...")
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("✅ ربات با موفقیت خاموش شد.")

# --- ۷. تابع اصلی اجرای برنامه ---
async def main():
    # ثبت رویدادهای شروع و پایان
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # ایجاد اپلیکیشن وب aiohttp
    app = web.Application()

    # تنظیم هندلر وب‌هوک (دریافت پیام‌های تلگرام)
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # اتصال ربات به اپلیکیشن وب
    setup_application(app, dp, bot=bot)

    # یک مسیر ساده برای Health Check (بررسی سلامت سرویس توسط Render)
    async def health_check(request):
        return web.Response(text="Bot is running!")
    app.router.add_get("/", health_check)

    # راه‌اندازی تسک پس‌زمینه
    asyncio.create_task(analysis_loop())

    # راه‌اندازی وب‌سرور روی پورت مناسب
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logger.info(f"🚀 وب‌سرور روی پورت {PORT} اجرا شد.")
    if WEBHOOK_URL:
        logger.info(f"🌐 آدرس وب‌هوک: {WEBHOOK_URL}")

    # نگه داشتن برنامه در حال اجرا (تا زمانی که متوقف شود)
    await asyncio.Event().wait()

# --- ۸. نقطه ورود برنامه ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("برنامه متوقف شد.")
