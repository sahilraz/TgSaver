"""Job queue, history, refresh, and cancellation handlers."""

from aiogram import Router, types
from aiogram.filters import Command
from app.bot.keyboards.inline import back_to_dashboard_keyboard, batch_action_keyboard
from app.bot.templates.messages import format_batch_progress
from app.database.repository import Repository
from app.database.session import get_db_session

router = Router()


@router.message(Command("queue"))
@router.callback_query(lambda c: c.data == "btn:queue")
async def handle_queue(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    async with get_db_session() as session:
        repo = Repository(session)
        batches = await repo.list_user_batches(user_id, limit=5)

    active_batches = [b for b in batches if b.status in ("QUEUED", "RUNNING")]

    if not active_batches:
        text = "📋 <b>Job Queue</b>\n\nNo active or queued jobs at this time."
    else:
        text = "📋 <b>Active Job Queue</b>\n\n"
        for b in active_batches:
            text += (
                f"• <b>Job <code>{b.id[:8]}</code></b>: {b.status}\n"
                f"  Items: {b.completed_items + b.failed_items + b.skipped_items}/{b.total_items}\n\n"
            )

    markup = back_to_dashboard_keyboard()
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.message(Command("history"))
async def handle_history(message: types.Message):
    user_id = message.from_user.id
    async with get_db_session() as session:
        repo = Repository(session)
        batches = await repo.list_user_batches(user_id, limit=10)

    if not batches:
        await message.answer("📜 <b>Job History</b>\n\nNo past archive jobs found.", reply_markup=back_to_dashboard_keyboard())
        return

    text = "📜 <b>Recent Archive History:</b>\n\n"
    for b in batches:
        mb = round(b.bytes_transferred / (1024 * 1024), 2)
        text += (
            f"• <code>{b.id[:8]}</code> | <b>{b.status}</b>\n"
            f"  Items: {b.completed_items}/{b.total_items} | Transferred: {mb} MB\n\n"
        )

    await message.answer(text, reply_markup=back_to_dashboard_keyboard())


@router.message(Command("cancel"))
async def handle_cancel_command(message: types.Message):
    args = message.text.replace("/cancel", "").strip()
    if not args:
        await message.answer("Usage: <code>/cancel &lt;job_id&gt;</code>")
        return

    user_id = message.from_user.id
    async with get_db_session() as session:
        repo = Repository(session)
        batches = await repo.list_user_batches(user_id, limit=20)
        target = next((b for b in batches if b.id.startswith(args)), None)

        if not target:
            await message.answer("❌ Job not found or does not belong to you.")
            return

        success = await repo.cancel_batch_job(target.id, user_id)

    if success:
        await message.answer(f"🛑 Job <code>{target.id[:8]}</code> successfully cancelled.")
    else:
        await message.answer(f"⚠️ Could not cancel job <code>{target.id[:8]}</code> (already finished or invalid).")


@router.callback_query(lambda c: c.data.startswith("job:cancel:"))
async def handle_cancel_callback(callback: types.CallbackQuery):
    short_id = callback.data.split(":")[2]
    user_id = callback.from_user.id

    async with get_db_session() as session:
        repo = Repository(session)
        batches = await repo.list_user_batches(user_id, limit=20)
        target = next((b for b in batches if b.id.startswith(short_id)), None)
        if target:
            await repo.cancel_batch_job(target.id, user_id)
            await callback.answer("Job cancelled.")
            await callback.message.edit_text(f"🛑 Job <code>{target.id[:8]}</code> has been cancelled.")
        else:
            await callback.answer("Job not found.", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("job:refresh:"))
async def handle_refresh_callback(callback: types.CallbackQuery):
    short_id = callback.data.split(":")[2]
    user_id = callback.from_user.id

    async with get_db_session() as session:
        repo = Repository(session)
        batches = await repo.list_user_batches(user_id, limit=20)
        target = next((b for b in batches if b.id.startswith(short_id)), None)

    if not target:
        await callback.answer("Job not found.", show_alert=True)
        return

    await callback.answer("Refreshed.")
    text = format_batch_progress(
        batch_id=target.id,
        completed=target.completed_items,
        failed=target.failed_items,
        skipped=target.skipped_items,
        total=target.total_items,
        bytes_transferred=target.bytes_transferred,
        elapsed=0.0,
    )
    try:
        await callback.message.edit_text(text, reply_markup=batch_action_keyboard(target.id))
    except Exception:
        pass
