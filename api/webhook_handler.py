"""FastAPI ASGI app handling Telegram webhooks and health endpoints."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request, Response
from aiogram.types import Update
from app.application import app as core_app
from app.bot.bot_instance import bot, dp
from app.config import settings
from app.monitoring.health import health_service


import logging
import re

logger = logging.getLogger(__name__)


def get_sanitized_secret_token() -> str | None:
    if not settings.WEBHOOK_SECRET:
        return None
    # Telegram Bot API allows only A-Z, a-z, 0-9, _ and -
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", settings.WEBHOOK_SECRET)
    return sanitized[:256] if sanitized else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await core_app.setup()
    await core_app.start_worker()

    if bot:
        webhook_base = settings.WEBHOOK_URL or "https://tgsaverbot.antideploy.app"
        webhook_endpoint = f"{webhook_base.rstrip('/')}/webhook"
        secret_tok = get_sanitized_secret_token()
        try:
            await bot.set_webhook(
                url=webhook_endpoint,
                secret_token=secret_tok,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "inline_query", "chat_member"],
            )
            logger.info(f"Telegram webhook active on: {webhook_endpoint}")
        except Exception as e:
            logger.error(f"Failed to register Telegram webhook: {e}")

    yield

    await core_app.shutdown()


web_app = FastAPI(title="TgSaverBot API", lifespan=lifespan)

@web_app.get("/health")
async def health_endpoint():
    return await health_service.check_liveness()


@web_app.get("/ready")
async def readiness_endpoint():
    return await health_service.check_readiness()


@web_app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=None),
):
    """Processes incoming Telegram updates via Webhook."""
    expected_secret = get_sanitized_secret_token()
    if expected_secret and x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token.")

    if not bot:
        raise HTTPException(status_code=500, detail="Bot token not configured.")

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        # Feed update asynchronously to Aiogram Dispatcher
        await dp.feed_update(bot=bot, update=update)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
