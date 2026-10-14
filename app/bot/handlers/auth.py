from aiogram import F, Router, types
from aiogram.filters import Command
from app.auth.login_service import login_service
from app.bot.keyboards.inline import (
    auth_code_keyboard,
    auth_keyboard,
    back_to_dashboard_keyboard,
    logout_options_keyboard,
)
from app.bot.templates.messages import format_account_info
from app.database.repository import Repository
from app.database.session import get_db_session

router = Router()


@router.message(Command("account"))
@router.callback_query(lambda c: c.data == "btn:account")
async def handle_account(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    async with get_db_session() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(user_id)
        sess = await repo.get_user_session(user_id)
        is_connected = user.is_connected
        sess_info = {
            "phone_number": sess.phone_number if sess else None,
            "account_id": sess.account_id if sess else None,
            "account_first_name": sess.account_first_name if sess else None,
        } if sess else None

    text = format_account_info(is_connected, sess_info)
    markup = auth_keyboard(is_connected)

    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=markup)
        except Exception:
            await event.message.answer(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.message(Command("login"))
@router.callback_query(lambda c: c.data == "btn:login")
async def handle_login_prompt(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    async with get_db_session() as session:
        repo = Repository(session)
        await repo.set_auth_state(user_id, state="AWAITING_PHONE")

    text = (
        "🔐 <b>Connect Your Telegram Account</b>\n\n"
        "Please send your phone number in international format (e.g., <code>+1234567890</code>).\n\n"
        "<i>Your phone number is processed in private temp memory and will never be logged or shared.</i>"
    )

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=auth_keyboard(False))
    else:
        await event.answer(text, reply_markup=auth_keyboard(False))


@router.callback_query(lambda c: c.data == "btn:login_cancel")
async def handle_cancel_login(callback: types.CallbackQuery):
    await callback.answer("Login cancelled.")
    user_id = callback.from_user.id
    await login_service.cancel_login(user_id)
    await callback.message.edit_text(
        "❌ Login process cancelled.", reply_markup=back_to_dashboard_keyboard()
    )


@router.callback_query(lambda c: c.data == "btn:login_resend")
async def handle_login_resend(callback: types.CallbackQuery):
    await callback.answer("Requesting verification code resend...")
    user_id = callback.from_user.id
    res = await login_service.resend_code(user_id)
    if res.success:
        await callback.message.answer(
            f"✅ {res.message}",
            reply_markup=auth_code_keyboard(),
        )
    else:
        await callback.message.answer(
            f"❌ {res.error}",
            reply_markup=auth_code_keyboard(),
        )


@router.message(Command("logout"))
@router.callback_query(lambda c: c.data == "btn:logout_menu")
async def handle_logout_menu(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    text = (
        "🚪 <b>Disconnect or Log Out</b>\n\n"
        "Choose an option:\n\n"
        "• <b>Disconnect (Keep Session):</b> Stops background processing while keeping your encrypted session saved for instant reconnection.\n\n"
        "• <b>Log Out Completely (Wipe Session):</b> Immediately calls Telegram MTProto logout, revokes the authorization, and permanently purges your encrypted session from the database."
    )
    markup = logout_options_keyboard()

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.callback_query(lambda c: c.data == "btn:disconnect_keep")
async def handle_disconnect_keep(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    await login_service.disconnect_account(user_id)
    await callback.message.edit_text(
        "⏸️ Account disconnected. Your encrypted session is preserved. Use /login to reconnect.",
        reply_markup=back_to_dashboard_keyboard(),
    )


@router.callback_query(lambda c: c.data == "btn:logout_full")
async def handle_logout_full(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    await login_service.logout_completely(user_id)
    await callback.message.edit_text(
        "🗑️ Successfully logged out. Your session has been revoked from Telegram and purged from the database.",
        reply_markup=back_to_dashboard_keyboard(),
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_auth_text_input(message: types.Message):
    user_id = message.from_user.id

    async with get_db_session() as session:
        repo = Repository(session)
        auth_state = await repo.get_auth_state(user_id)

    if not auth_state or auth_state.state == "IDLE":
        from app.bot.handlers.save import process_submitted_links
        handled = await process_submitted_links(message)
        if not handled:
            await message.answer(
                "Send Telegram post links to archive, or use /help to view commands.",
                reply_markup=back_to_dashboard_keyboard(),
            )
        return

    if auth_state.state == "AWAITING_PHONE":
        res = await login_service.start_login(user_id, message.text)
        if res.success:
            await message.answer(
                res.message,
                reply_markup=auth_code_keyboard(),
            )
        else:
            await message.answer(f"❌ {res.error}", reply_markup=auth_keyboard(False))
        return

    if auth_state.state == "AWAITING_CODE":
        res = await login_service.submit_code(user_id, message.text)
        if res.success:
            if res.needs_password:
                await message.answer(
                    "🔐 Two-Step Verification (2FA) is enabled.\nPlease enter your Telegram 2FA password:",
                    reply_markup=auth_keyboard(False),
                )
            else:
                await message.answer(
                    f"✅ {res.message}",
                    reply_markup=back_to_dashboard_keyboard(),
                )
        else:
            await message.answer(f"❌ {res.error}", reply_markup=auth_code_keyboard())
        return

    if auth_state.state == "AWAITING_PASSWORD":
        res = await login_service.submit_password(user_id, message.text)
        if res.success:
            await message.answer(
                f"✅ {res.message}",
                reply_markup=back_to_dashboard_keyboard(),
            )
        else:
            await message.answer(f"❌ {res.error}", reply_markup=auth_keyboard(False))
        return
