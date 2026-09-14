import os
import asyncio
import logging
from datetime import datetime, timedelta
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FETCH_INTERVAL_MINUTES
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

# ══════════════════════════════════════════════
# کش و وضعیت
# ══════════════════════════════════════════════
last_analysis = {
    "signal": None,
    "price": None,
    "timestamp": None,
    "data": None,
}

# برای هشدار نوسان شدید
price_history = []  # لیست از (timestamp, price)
SHARP_MOVE_THRESHOLD = 1.0   # درصد
SHARP_MOVE_WINDOW_MIN = 15   # دقیقه

# برای گزارش روزانه
DAILY_REPORT_HOUR = 9        # ساعت ۹ صبح
last_daily_report_date = None

# وضعیت روز (برای گزارش روزانه)
daily_stats = {
    "open": None,
    "high": None,
    "low": None,
    "close": None,
    "start_date": None,
    "signals_count": 0,
    "bullish_count": 0,
    "bearish_count": 0,
}


def reset_daily_stats(price):
    """شروع آمار روز جدید."""
    daily_stats["open"] = price
    daily_stats["high"] = price
    daily_stats["low"] = price
    daily_stats["close"] = price
    daily_stats["start_date"] = datetime.now().date()
    daily_stats["signals_count"] = 0
    daily_stats["bullish_count"] = 0
    daily_stats["bearish_count"] = 0


def update_daily_stats(price):
    """به‌روزرسانی آمار روز."""
    if daily_stats["open"] is None:
        reset_daily_stats(price)
    else:
        if price > daily_stats["high"]:
            daily_stats["high"] = price
        if price < daily_stats["low"]:
            daily_stats["low"] = price
        daily_stats["close"] = price


# ══════════════════════════════════════════════
# هشدار نوسان شدید
# ══════════════════════════════════════════════
def check_sharp_movement(current_price):
    """
    چک می‌کنه اگه قیمت در بازه زمانی کوتاه تغییر شدیدی داشته باشه.
    برمی‌گردونه: (متن هشدار یا None)
    """
    global price_history

    now = datetime.now()

    # اضافه کردن قیمت جدید
    price_history.append((now, current_price))

    # پاک کردن رکوردهای قدیمی‌تر از پنجره
    cutoff = now - timedelta(minutes=SHARP_MOVE_WINDOW_MIN)
    price_history = [(t, p) for t, p in price_history if t >= cutoff]

    # نیاز به حداقل ۲ نقطه
    if len(price_history) < 2:
        return None

    oldest_price = price_history[0][1]
    change_pct = (current_price - oldest_price) / oldest_price * 100

    if abs(change_pct) >= SHARP_MOVE_THRESHOLD:
        emoji = "🚀" if change_pct > 0 else "💥"
        direction = "صعودی" if change_pct > 0 else "نزولی"
        return (
            f"{emoji} **هشدار نوسان شدید!**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 حرکت {direction}: **{change_pct:+.2f}%**\n"
            f"💰 قیمت فعلی: **{current_price:,.0f}** تومان\n"
            f"📉 قیمت {SHARP_MOVE_WINDOW_MIN} دقیقه پیش: **{oldest_price:,.0f}**\n"
            f"🕐 {now.strftime('%H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _نوسان غیرعادی تشخیص داده شد._"
        )
    return None


# ══════════════════════════════════════════════
# گزارش روزانه
# ══════════════════════════════════════════════
def build_daily_report():
    """ساخت متن گزارش روزانه."""
    if daily_stats["open"] is None:
        return None

    o = daily_stats["open"]
    h = daily_stats["high"]
    l = daily_stats["low"]
    c = daily_stats["close"]

    if o is None or c is None:
        return None

    change = (c - o) / o * 100
    emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪️"
    date_str = daily_stats["start_date"].strftime("%Y-%m-%d") if daily_stats["start_date"] else "—"

    lines = [
        f"📊 **گزارش روزانه طلا**",
        f"📅 {date_str}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔓 باز:    **{o:,.0f}**",
        f"🔒 بسته:   **{c:,.0f}**",
        f"⬆️ بیشترین: **{h:,.0f}**",
        f"⬇️ کمترین:  **{l:,.0f}**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} تغییر روز: **{change:+.2f}%**",
        "",
        f"📈 سیگنال‌های روز: **{daily_stats['signals_count']}**",
        f"  🟢 صعودی: {daily_stats['bullish_count']}",
        f"  🔴 نزولی: {daily_stats['bearish_count']}",
    ]

    # دامنه نوسان
    if o > 0:
        volatility = (h - l) / o * 100
        lines.append(f"\n📉 دامنه نوسان: **{volatility:.2f}%**")

    return "\n".join(lines)


async def check_daily_report():
    """اگه ساعت ۹ صبح بود و امروز گزارش نداده، بفرست."""
    global last_daily_report_date

    now = datetime.now()

    # ساعت ۹ صبح به بعد
    if now.hour != DAILY_REPORT_HOUR:
        return

    # امروز قبلاً گزارش داده شده؟
    if last_daily_report_date == now.date():
        return

    # داده کافی هست؟
    if daily_stats["open"] is None:
        return

    report = build_daily_report()
    if report:
        await send_telegram_message_async(report)
        logger.info("📊 گزارش روزانه ارسال شد")
        last_daily_report_date = now.date()

        # ریست آمار برای روز جدید
        # (تا پایان امروز جمع می‌کنیم، فردا صبح گزارش می‌ده)
        # این خط رو کامنت می‌کنیم که آمار امروز رو از دست نده
        # reset_daily_stats(daily_stats["close"])


# ══════════════════════════════════════════════
# دستور /start
# ══════════════════════════════════════════════
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🟢 **ربات تحلیل طلا فعال است!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "من هر ۱۵ دقیقه بازار طلا رو تحلیل می‌کنم و "
        "در صورت مشاهده سیگنال قوی، برات پیام می‌فرستم.\n\n"
        "📊 **قابلیت‌های جدید:**\n"
        "• گزارش روزانه خودکار (ساعت ۹ صبح)\n"
        "• هشدار نوسان شدید (>۱٪ در ۱۵ دقیقه)\n\n"
        "📌 برای دیدن راهنما، دستور /help رو بزن."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ══════════════════════════════════════════════
# دستور /help
# ══════════════════════════════════════════════
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 **راهنمای ربات تحلیل طلا**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**دستورات موجود:**\n\n"
        "💹 /price\n"
        "   قیمت لحظه‌ای طلا، انس، دلار و DXY\n\n"
        "📊 /analyze\n"
        "   تحلیل کامل و فوری (تکنیکال + فاندامنتال + SMC)\n\n"
        "🎯 /signal\n"
        "   آخرین سیگنال تولیدشده با جزئیات\n\n"
        "📈 /report\n"
        "   گزارش امروز (باز، بسته، بیشترین، کمترین)\n\n"
        "⚙️ /status\n"
        "   وضعیت ربات و زمان آخرین به‌روزرسانی\n\n"
        "ℹ️ /help\n"
        "   همین راهنما\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 **هشدارهای خودکار:**\n"
        "• سیگنال قوی (اطمینان >۶۰٪)\n"
        "• نوسان شدید (>۱٪ در ۱۵ دقیقه)\n"
        "• گزارش روزانه (ساعت ۹ صبح)\n\n"
        "⏰ **به‌روزرسانی خودکار:** هر ۱۵ دقیقه\n"
        "🔇 **ضد اسپم:** حداقل ۱ ساعت بین هشدارهای مشابه\n\n"
        "⚠️ این ربات کمک‌تحلیلگر است، نه تضمین سود."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ══════════════════════════════════════════════
# دستور /price
# ══════════════════════════════════════════════
async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ در حال دریافت قیمت‌ها...")

    try:
        data = fetch_all_data()

        gold = data.get("gold_18k") or {}
        ounce = data.get("gold_ounce") or {}
        usd = data.get("usd") or {}
        dxy = data.get("dxy") or {}

        lines = [
            "💹 **قیمت لحظه‌ای بازار**",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        if gold.get("price"):
            lines.append(f"🥇 طلای ۱۸ عیار: **{gold['price']:,.0f}** تومان")
        if ounce.get("price"):
            lines.append(f"🌍 انس جهانی: **${ounce['price']:,.2f}**")
        if usd.get("price"):
            lines.append(f"💵 دلار آزاد: **{usd['price']:,.0f}** تومان")
        if dxy.get("price"):
            lines.append(f"📉 شاخص دلار: **{dxy['price']:.2f}**")

        lines.append("━━━━━━━━━━━━━━━━━━━━")

        if gold.get("price") and ounce.get("price") and usd.get("price"):
            try:
                intrinsic = (ounce["price"] * usd["price"]) / 31.1035 * 0.75
                bubble = (gold["price"] / intrinsic - 1) * 100
                if bubble > 15:
                    emoji = "🔴"
                elif bubble < -5:
                    emoji = "🟢"
                else:
                    emoji = "🟡"
                lines.append(f"{emoji} حباب طلا: **{bubble:+.2f}%**")
            except Exception:
                pass

        lines.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"price_cmd error: {e}")
        await update.message.reply_text(
            f"❌ خطا در دریافت قیمت:\n`{str(e)[:200]}`",
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════
# دستور /analyze
# ══════════════════════════════════════════════
async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 در حال تحلیل کامل بازار... لطفاً صبر کن.")

    try:
        data = fetch_all_data()

        if not data.get("gold_18k"):
            await update.message.reply_text("❌ قیمت طلا دریافت نشد. بعداً تلاش کن.")
            return

        price = data["gold_18k"]["price"]
        save_price_data(data)
        df = get_historical_data(days=90)

        tech = run_technical_analysis(df)
        fund = compute_fundamental_score(data, df)
        smc_r = compute_smc_score(df)
        signal = signal_engine.combine(tech, fund, smc_r)

        last_analysis["signal"] = signal
        last_analysis["price"] = price
        last_analysis["timestamp"] = datetime.now().isoformat()
        last_analysis["data"] = data

        msg = signal_engine.format_message(signal, price)
        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"analyze_cmd error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ خطا در تحلیل:\n`{str(e)[:200]}`",
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════
# دستور /signal
# ══════════════════════════════════════════════
async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not last_analysis["signal"]:
        text = (
            "📭 **هنوز سیگنالی تولید نشده**\n\n"
            "اولین تحلیل خودکار تا ۱۵ دقیقه دیگه انجام می‌شه.\n"
            "یا با دستور /analyze همین الان تحلیل بگیر."
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    msg = signal_engine.format_message(
        last_analysis["signal"],
        last_analysis["price"]
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ══════════════════════════════════════════════
# دستور /report
# ══════════════════════════════════════════════
async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = build_daily_report()
    if not report:
        await update.message.reply_text(
            "📭 هنوز داده‌ای برای گزارش امروز جمع نشده.\n"
            "چند دقیقه دیگه دوباره امتحان کن."
        )
        return
    await update.message.reply_text(report, parse_mode="Markdown")


# ══════════════════════════════════════════════
# دستور /status
# ══════════════════════════════════════════════
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if last_analysis["timestamp"]:
        last_time = last_analysis["timestamp"][:19].replace("T", " ")
    else:
        last_time = "هنوز اجرا نشده"

    if last_analysis["signal"]:
        direction = last_analysis["signal"]["direction"]
        confidence = last_analysis["signal"]["confidence"]
        signal_line = f"{direction} ({confidence}%)"
    else:
        signal_line = "—"

    text = (
        "⚙️ **وضعیت ربات**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 وضعیت: فعال\n"
        f"⏰ فاصله تحلیل: هر {FETCH_INTERVAL_MINUTES} دقیقه\n"
        f"🕐 آخرین تحلیل: {last_time}\n"
        f"🎯 آخرین سیگنال: {signal_line}\n"
        f"📊 سیگنال‌های امروز: {daily_stats['signals_count']}\n"
        f"🔔 هشدار نوسان: >{SHARP_MOVE_THRESHOLD}٪ در {SHARP_MOVE_WINDOW_MIN} دقیقه\n"
        f"📈 گزارش روزانه: ساعت {DAILY_REPORT_HOUR}:۰۰\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "همه چیز خوبه! ✅"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ══════════════════════════════════════════════
# حلقه تحلیل خودکار
# ══════════════════════════════════════════════
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
                update_daily_stats(price)

                df = get_historical_data(days=90)
                tech = run_technical_analysis(df)
                fund = compute_fundamental_score(data, df)
                smc_r = compute_smc_score(df)
                signal = signal_engine.combine(tech, fund, smc_r)

                last_analysis["signal"] = signal
                last_analysis["price"] = price
                last_analysis["timestamp"] = datetime.now().isoformat()
                last_analysis["data"] = data

                logger.info(f"📊 جهت: {signal['direction']} | "
                            f"اطمینان: {signal['confidence']}%")

                # ─── هشدار نوسان شدید ───
                sharp_msg = check_sharp_movement(price)
                if sharp_msg:
                    await send_telegram_message_async(sharp_msg)
                    logger.info("⚠️ هشدار نوسان شدید ارسال شد")

                # ─── سیگنال معمولی ───
                if signal_engine.should_alert(signal):
                    msg = signal_engine.format_message(signal, price)
                    await send_telegram_message_async(msg)
                    logger.info("✅ هشدار سیگنال ارسال شد")

                    # به‌روزرسانی آمار روز
                    daily_stats["signals_count"] += 1
                    if signal["direction"] == "صعودی":
                        daily_stats["bullish_count"] += 1
                    elif signal["direction"] == "نزولی":
                        daily_stats["bearish_count"] += 1

            else:
                logger.warning("⚠️ قیمت دریافت نشد")

            # ─── گزارش روزانه ───
            await check_daily_report()

        except Exception as e:
            logger.error(f"❌ خطا: {e}", exc_info=True)

        await asyncio.sleep(FETCH_INTERVAL_MINUTES * 60)


# ══════════════════════════════════════════════
# وب‌سرور (برای Render)
# ══════════════════════════════════════════════
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
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("price", price_cmd))
    application.add_handler(CommandHandler("analyze", analyze_cmd))
    application.add_handler(CommandHandler("signal", signal_cmd))
    application.add_handler(CommandHandler("report", report_cmd))
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


if __name__ == "__main__":
    asyncio.run(main())
