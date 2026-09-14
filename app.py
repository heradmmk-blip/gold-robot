import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, FETCH_INTERVAL_MINUTES
from data_fetcher import init_db, fetch_all_data, save_price_data, get_historical_data
from technical_engine import run_technical_analysis
from fundamental_engine import compute_fundamental_score
from smc_engine import compute_smc_score
from signal_engine import SignalEngine
from telegram_notifier import send_telegram_message_async

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app")

PORT = int(os.environ.get("PORT", 8443))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

signal_engine = SignalEngine()


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 ربات تحلیل طلا فعال است!\n"
        "از این پس سیگنال‌ها به صورت خودکار ارسال می‌شوند."
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ ربات در حال اجراست.")


async def analysis_loop():
    logger.info("🔄 شروع حلقه تحلیل...")
    await asyncio.sleep(30)
    while True:
        try:
            logger.info("=" * 40)
            data = fetch_all_data()
            if data.get("gold_18k"):
                price = data["gold_18k"]["price"]
                logger.info(f"💰 قیمت طلا: {price:,.0f}")
                save_price_data(data)
                df = get_historical_data(days=90)
                tech = run_technical_analysis(df)
                fund = compute_fundamental_score(data, df)
                smc_r = compute_smc_score(df)
                signal = signal_engine.combine(tech, fund, smc_r)
                logger.info(f"📊 جهت: {signal['direction']} | "
                            f"اطمینان: {signal['confidence']}%")
                if signal_engine.should_alert(signal):
                    msg = signal_engine.format_message(signal, price)
                    await send_telegram_message_async(msg)
                    logger.info("✅ هشدار ارسال شد")
            else:
                logger.warning("⚠️ قیمت دریافت نشد")
        except Exception as e:
            logger.error(f"❌ خطا: {e}", exc_info=True)
        await asyncio.sleep(FETCH_INTERVAL_MINUTES * 60)


async def health(request):
    return web.Response(text="Bot is running")


async def webhook_handler(request):
    try:
        data = await request.json()
        update = Update.de_json(data, request.app["telegram_app"].bot)
        await request.app["telegram_app"].process_update(update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return web.Response(text="OK")


async def main():
    init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("status", status_cmd))

    await application.initialize()
    await application.start()

    webhook_path = f"/{TELEGRAM_BOT_TOKEN}"

    if RENDER_URL:
        webhook_url = f"{RENDER_URL}{webhook_path}"
        await application.bot.set_webhook(url=webhook_url)
        logger.info(f"🔗 Webhook تنظیم شد: {webhook_url}")

    app = web.Application()
    app["telegram_app"] = application
    app.router.add_get("/", health)
    app.router.add_post(webhook_path, webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"✅ وب‌سرور روی پورت {PORT}")

    asyncio.create_task(analysis_loop())

    await asyncio.Event().wait()


if __import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
