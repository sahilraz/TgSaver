"""Aiogram Bot and Dispatcher initialization."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.config import settings

bot: Bot = None

if settings.BOT_TOKEN:
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

dp = Dispatcher()

_bot_username = None

async def get_bot_username() -> str:
    global _bot_username
    if _bot_username:
        return _bot_username
    if bot:
        try:
            me = await bot.get_me()
            if me and me.username:
                _bot_username = me.username
                return _bot_username
        except Exception:
            pass
    return "TgSaverBot"
