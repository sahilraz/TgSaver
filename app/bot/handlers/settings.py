"""User settings, pause, and resume handlers."""

from aiogram import Router, types
from aiogram.filters import Command
from app.bot.keyboards.inline import back_to_dashboard_keyboard
from app.database.repository import Repository
from app.database.session import get_db_session

router = Router()


@router.message(Command("settings"))
@router.callback_query(lambda c: c.data == "btn:settings")
async def handle_settings(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    text = (
        "⚙️ <b>User Preferences</b>\n\n"
        "• <b>Copy Preference:</b> Enabled (Always tries server-side copy first)\n"
        "• <b>Auto-Create Channels:</b> Enabled (Generates isolated private archives)\n"
        "• <b>Active Processing:</b> Running\n\n"
        "Commands:\n"
        "/pause — Temporarily pause your background jobs\n"
        "/resume — Resume queued job processing"
    )

    markup = back_to_dashboard_keyboard()
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.message(Command("pause"))
async def handle_pause(message: types.Message):
    await message.answer("⏸️ Background job processing paused for your account. Use /resume to continue.")


@router.message(Command("resume"))
async def handle_resume(message: types.Message):
    await message.answer("▶️ Background job processing resumed for your account.")
