"""
i18n Middleware - Har bir xabarda foydalanuvchi tilini avtomatik aniqlaydi.
Barcha Message turlari (text, location, contact, photo va h.k.) va CallbackQuery qamrab olinadi.
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.core.database import AsyncSessionLocal
from app.crud.user import UserCRUD
from app.bot.messages import normalize_bot_lang


class I18nMiddleware(BaseMiddleware):
    """Foydalanuvchi tilini bazadan olib, data['lang'] ga qo'shadi. Message (matn, lokatsiya, kontakt) va CallbackQuery uchun ishlaydi."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        # Message: text, location, contact, photo va boshqa barcha turdagi xabarlar
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        lang = "uz"
        if user_id is not None:
            async with AsyncSessionLocal() as db:
                user = await UserCRUD.get_by_telegram_id(db, user_id)
                if user and getattr(user, "language_code", None):
                    lang = normalize_bot_lang(user.language_code)

        data["lang"] = lang
        return await handler(event, data)
