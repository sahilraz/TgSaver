from typing import List
from aiogram import Router, types
from aiogram.filters import Command
from app.bot.keyboards.inline import batch_action_keyboard, back_to_dashboard_keyboard
from app.bot.templates.messages import format_batch_progress
from app.database.repository import Repository
from app.database.session import get_db_session
from app.jobs.queue import job_queue
from app.security.validation import extract_telegram_links

router = Router()


@router.callback_query(lambda c: c.data == "btn:save_guide")
async def handle_save_guide(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⚡ <b>How to Archive Posts:</b>\n\n"
        "Simply send one or multiple Telegram post links into this chat:\n\n"
        "<code>https://t.me/channelname/123</code>\n"
        "<code>https://t.me/c/1234567890/456</code>\n\n"
        "<i>You can send multiple links separated by spaces or newlines.</i>",
        reply_markup=back_to_dashboard_keyboard(),
    )


@router.message(Command("save"))
async def handle_save_command(message: types.Message):
    links = message.text.replace("/save", "").strip()
    if not links:
        await message.answer(
            "Please provide one or more Telegram post links after /save:\n"
            "Example: <code>/save https://t.me/channel/123</code>"
        )
        return

    await process_submitted_links(message, raw_text=links)


async def process_submitted_links(message: types.Message, raw_text: str = None) -> bool:
    text_to_parse = raw_text or message.text or ""
    parsed_links = extract_telegram_links(text_to_parse)

    if not parsed_links:
        return False

    user_id = message.from_user.id

    async with get_db_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(user_id)
        if not user.is_connected:
            await message.answer(
                "⚠️ <b>Account Not Connected</b>\n\n"
                "Please connect your Telegram account first to archive posts via this bot.",
                reply_markup=back_to_dashboard_keyboard(),
            )
            return True

        items_data = [
            {
                "source_url": p.raw_url,
                "source_channel_ref": p.channel_ref,
                "source_message_id": p.message_id,
            }
            for p in parsed_links
        ]

        batch = await repo.create_batch_job(user_id, items_data)
        batch_id = batch.id
        total_items = len(parsed_links)

    initial_text = format_batch_progress(
        batch_id=batch_id,
        completed=0,
        failed=0,
        skipped=0,
        total=total_items,
        bytes_transferred=0,
        elapsed=0.0,
    )
    sent_msg = await message.answer(
        initial_text,
        reply_markup=batch_action_keyboard(batch_id),
    )

    async with get_db_session() as session:
        repo = Repository(session)
        b = await repo.get_batch_job(batch_id)
        if b:
            b.status_message_id = sent_msg.message_id

    await job_queue.enqueue_batch(batch_id)
    return True
