"""Mijozga yuborilgan kuzatish xabarini safar tugaganda chatdan olib tashlash."""
from typing import Optional

from aiogram import Bot

from app.core.logger import get_logger

logger = get_logger(__name__)


async def clear_user_tracking_message(bot: Bot, chat_id: int, message_id: Optional[int]) -> None:
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception as e2:
            logger.warning(
                "Tracking xabarini tozalashda xato: chat=%s mid=%s: %s",
                chat_id,
                message_id,
                e2,
            )
