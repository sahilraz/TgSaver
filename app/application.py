import asyncio
import logging
from typing import Optional
from app.auth.session_manager import client_manager
from app.bot.bot_instance import bot, dp
from app.bot.handlers import register_all_handlers
from app.bot.keyboards.inline import batch_action_keyboard
from app.bot.templates.messages import format_batch_progress
from app.config import settings
from app.database.session import close_db, get_db_session, init_db
from app.database.repository import Repository
from app.jobs.queue import job_queue
from app.jobs.workers import batch_worker

logger = logging.getLogger(__name__)


async def notify_batch_progress(
    batch_id: str,
    user_id: int,
    completed: int,
    failed: int,
    skipped: int,
    total: int,
    bytes_transferred: int,
    elapsed: float,
    final_status: Optional[str] = None,
    destination_channel_id: Optional[int] = None,
    destination_message_id: Optional[int] = None,
):
    if not bot:
        return

    try:
        async with get_db_session() as session:
            repo = Repository(session)
            batch = await repo.get_batch_job(batch_id)
            if not batch or not batch.status_message_id:
                return
            msg_id = batch.status_message_id

        if final_status:
            from app.bot.keyboards.inline import batch_completed_keyboard
            from app.bot.templates.messages import format_batch_completed

            text = format_batch_completed(
                batch_id=batch_id,
                completed=completed,
                failed=failed,
                skipped=skipped,
                total=total,
                bytes_transferred=bytes_transferred,
                elapsed=elapsed,
                status=final_status,
            )

            # Generate Telegram channel deep link if destination info is available
            view_url = None
            if destination_channel_id and destination_message_id:
                raw_id_str = str(destination_channel_id).replace("-100", "")
                view_url = f"https://t.me/c/{raw_id_str}/{destination_message_id}"

            await bot.edit_message_text(
                text=text,
                chat_id=user_id,
                message_id=msg_id,
                reply_markup=batch_completed_keyboard(view_url=view_url),
            )
        else:
            text = format_batch_progress(
                batch_id=batch_id,
                completed=completed,
                failed=failed,
                skipped=skipped,
                total=total,
                bytes_transferred=bytes_transferred,
                elapsed=elapsed,
            )
            await bot.edit_message_text(
                text=text,
                chat_id=user_id,
                message_id=msg_id,
                reply_markup=batch_action_keyboard(batch_id),
            )
    except Exception as e:
        logger.debug(f"Progress edit throttled or skipped: {e}")



class Application:
    def __init__(self):
        self._worker_task: Optional[asyncio.Task] = None

    async def setup(self) -> None:
        logging.basicConfig(
            level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logger.info(f"Starting TgSaverBot in {settings.effective_profile.value.upper()} profile.")
        await init_db()
        await job_queue.connect()
        register_all_handlers(dp)
        batch_worker.set_notifier(notify_batch_progress)

    async def start_worker(self) -> None:
        self._worker_task = asyncio.create_task(batch_worker.start())

    async def run_polling(self) -> None:
        await self.setup()
        await self.start_worker()

        if not bot:
            raise RuntimeError("BOT_TOKEN is not configured! Please provide BOT_TOKEN in .env.")

        try:
            logger.info("Bot polling started.")
            await dp.start_polling(bot)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        logger.info("Shutting down TgSaverBot...")
        await batch_worker.stop()
        if self._worker_task:
            self._worker_task.cancel()

        await client_manager.close_all()
        await job_queue.close()
        await close_db()
        if bot:
            await bot.session.close()
        logger.info("Shutdown complete.")


app = Application()
