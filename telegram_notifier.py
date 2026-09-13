import logging
from telegram import Bot
from telegram.constants import ParseMode
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


async def send_telegram_message_async(message):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                               text=message,
                               parse_mode=ParseMode.MARKDOWN)
        logger.info("✅ پیام ارسال شد")
        return True
    except Exception as e:
        logger.error(f"❌ ارسال failed: {e}")
        return False
