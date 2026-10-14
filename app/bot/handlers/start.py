"""Start and dashboard command handlers."""

from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from app.bot.keyboards.inline import main_dashboard_keyboard
from app.bot.templates.messages import format_dashboard
from app.database.repository import Repository
from app.database.session import get_db_session

router = Router()


@router.message(CommandStart())
@router.message(Command("dashboard"))
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "User"

    async with get_db_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(user_id, username, first_name)
        stats = await repo.get_user_statistics(user_id)
        is_connected = user.is_connected

    text = format_dashboard(first_name, is_connected, stats)
    await message.answer(text, reply_markup=main_dashboard_keyboard(is_connected))


@router.callback_query(lambda c: c.data == "btn:dashboard")
async def handle_dashboard_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "User"

    async with get_db_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(user_id)
        stats = await repo.get_user_statistics(user_id)
        is_connected = user.is_connected

    text = format_dashboard(first_name, is_connected, stats)
    try:
        await callback.message.edit_text(text, reply_markup=main_dashboard_keyboard(is_connected))
    except Exception:
        await callback.message.answer(text, reply_markup=main_dashboard_keyboard(is_connected))
