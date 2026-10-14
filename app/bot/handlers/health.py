"""System health, ping, help, and privacy handlers."""

import time
from aiogram import Router, types
from aiogram.filters import Command
from app.bot.keyboards.inline import back_to_dashboard_keyboard
from app.bot.templates.messages import format_help, format_privacy
from app.monitoring.health import health_service

router = Router()


@router.message(Command("ping"))
async def handle_ping(message: types.Message):
    start = time.perf_counter()
    sent = await message.answer("🏓 Pong!")
    latency_ms = max(1, int((time.perf_counter() - start) * 1000))
    await sent.edit_text(f"🏓 Pong!  ·  {latency_ms}ms")


@router.message(Command("help"))
@router.callback_query(lambda c: c.data == "btn:help")
async def handle_help(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.CallbackQuery):
        await event.answer()
    text = format_help()
    markup = back_to_dashboard_keyboard()
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.message(Command("privacy"))
@router.callback_query(lambda c: c.data == "btn:privacy")
async def handle_privacy(event: types.Message | types.CallbackQuery):
    if isinstance(event, types.CallbackQuery):
        await event.answer()
    text = format_privacy()
    markup = back_to_dashboard_keyboard()
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.message(Command("health"))
async def handle_health(message: types.Message):
    res = await health_service.check_readiness()
    status_icon = "🟢" if res["status"] == "ready" else "🟡"
    db_icon = "✅" if res["database"]["ok"] else "❌"

    text = (
        f"{status_icon} <b>System Health Status</b>\n\n"
        f"• Platform Profile: <code>{res['profile'].upper()}</code>\n"
        f"• Database: {db_icon}\n"
        f"• CPU Load: <code>{res['host_resources']['cpu_percent']}%</code>\n"
        f"• RAM Usage: <code>{res['host_resources']['memory_used_percent']}%</code>\n"
        f"• Free Disk Space: <code>{res['host_resources']['disk_free_gb']} GB</code>\n"
    )
    await message.answer(text, reply_markup=back_to_dashboard_keyboard())
