"""Archive channel mappings handler."""

from aiogram import Router, types
from aiogram.filters import Command
from app.bot.keyboards.inline import back_to_dashboard_keyboard
from app.database.repository import Repository
from app.database.session import get_db_session
from app.security.validation import safe_html

router = Router()


@router.message(Command("archives"))
@router.callback_query(lambda c: c.data == "btn:archives")
async def handle_archives(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    async with get_db_session() as session:
        repo = Repository(session)
        mappings = await repo.list_mappings(user_id)

    if not mappings:
        text = (
            "📁 <b>My Archive Channels</b>\n\n"
            "No private archive channels created yet.\n"
            "When you archive a post, TgSaverBot will automatically create and map a private channel for it!"
        )
    else:
        text = "📁 <b>Your Private Archive Channels:</b>\n\n"
        for m in mappings:
            src = safe_html(m.source_title or m.source_channel_ref)
            dst = safe_html(m.destination_title or str(m.destination_channel_id))
            text += f"• <b>{src}</b> ➔ <i>{dst}</i>\n"

    markup = back_to_dashboard_keyboard()
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)
