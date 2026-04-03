"""Bazadagi foydalanuvchi tili — barcha handlerlar uchun yagona manba (default: uz)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.messages import normalize_bot_lang
from app.crud.user import UserCRUD


async def db_lang_for_telegram(db: AsyncSession, telegram_id: int) -> str:
    user = await UserCRUD.get_by_telegram_id(db, telegram_id)
    if user and getattr(user, "language_code", None):
        return normalize_bot_lang(user.language_code)
    return "uz"
