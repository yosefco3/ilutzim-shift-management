"""
Bot middleware: block unregistered or inactive users.
"""

import logging

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger("ilutzim")


class AuthMiddleware(BaseMiddleware):
    """Check that the Telegram user exists in our DB and is active."""

    async def __call__(self, handler, event, data):
        tg_id = None
        if isinstance(event, Message):
            tg_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            tg_id = event.from_user.id if event.from_user else None

        if tg_id is None:
            return await handler(event, data)

        # Lazy import to avoid circular deps
        from app.services.user_service import UserService
        from app.repositories.user_repository import UserRepository
        from app.database import get_session

        try:
            async with get_session() as session:
                user_svc = UserService(UserRepository(session))
                user = await user_svc.get_by_telegram_id(tg_id)
        except Exception as exc:
            logger.warning("AuthMiddleware DB error: %s – letting request through", exc)
            return await handler(event, data)

        if user is not None and not user.is_active:
            if isinstance(event, Message):
                await event.answer("🚫 החשבון שלך מושבת. פנה למנהל.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 החשבון שלך מושבת.", show_alert=True)
            return

        data["user"] = user
        return await handler(event, data)