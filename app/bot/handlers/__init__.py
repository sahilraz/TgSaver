"""Registers all bot routers into the main dispatcher."""

from aiogram import Dispatcher
from app.bot.handlers import archives, auth, health, jobs, save, settings, start, stats


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(save.router)
    dp.include_router(auth.router)
    dp.include_router(jobs.router)
    dp.include_router(archives.router)
    dp.include_router(stats.router)
    dp.include_router(settings.router)
    dp.include_router(health.router)
