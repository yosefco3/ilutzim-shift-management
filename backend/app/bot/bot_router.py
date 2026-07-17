"""
Bot lifecycle management – build dispatcher, register handlers, start/stop.
"""

import logging

from aiogram import Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.bot.bot_instance import get_bot
from app.bot.core import router as main_router
from app.bot.middlewares.auth import AuthMiddleware

logger = logging.getLogger("ilutzim")

_dispatcher: Dispatcher | None = None


def get_dispatcher() -> Dispatcher:
    """Build and return the aiogram Dispatcher with all routers and middleware."""
    global _dispatcher
    if _dispatcher is not None:
        return _dispatcher

    dp = Dispatcher()

    # Register middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Register routers.
    # Stage 3 — attendance punch/consent handlers, only when the feature is on.
    # MUST be included BEFORE main_router: core has a catch-all "לא הבנתי"
    # message handler that would otherwise swallow the punch-button texts.
    # The attendance router only matches its own button texts / FSM states,
    # so putting it first cannot shadow anything else.
    from app.config import get_settings

    if get_settings().ATTENDANCE_ENABLED:
        from app.bot.handlers.attendance import router as attendance_router

        dp.include_router(attendance_router)

    # Procedure-quiz (סד"פ) handlers, only when the feature is on. MUST be
    # included BEFORE main_router: core has a catch-all "לא הבנתי" message
    # handler; this router matches its own menu/quiz callbacks. Registering it
    # before polling also makes aiogram include "poll_answer" in allowed_updates.
    if get_settings().PROCEDURES_ENABLED:
        from app.bot.handlers.procedures import router as procedures_router

        dp.include_router(procedures_router)

    dp.include_router(main_router)

    _dispatcher = dp
    logger.info("Bot dispatcher initialized with handlers and middleware")
    return dp


async def start_bot():
    """Start polling in the background (no webhook)."""
    bot = get_bot()
    dp = get_dispatcher()

    # Delete any existing webhook
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Telegram bot starting polling...")

    # Start polling as a background task
    import asyncio
    asyncio.create_task(dp.start_polling(bot))
    logger.info("Telegram bot polling started")


async def stop_bot():
    """Stop the bot gracefully."""
    global _dispatcher
    if _dispatcher is not None:
        await _dispatcher.stop_polling()
        _dispatcher = None
        logger.info("Telegram bot polling stopped")