"""Haydovchi reply klaviaturasini safar tugagach majburan tiklash (Telegram + idempotent retrylar)."""

from __future__ import annotations

import hashlib
import traceback
from typing import Optional

from aiogram import Bot
from aiogram.types import ReplyKeyboardRemove

from app.bot.keyboards.driver_keyboards import driver_keyboard_online_with_taximeter
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Ko‘rinmas ajratuvchi — Telegram matnsiz xabarni rad etmasligi uchun
_KB_PLACEHOLDER = "\u2060"


def _bot_token_fingerprint() -> str:
    tok = (getattr(settings, "TELEGRAM_BOT_TOKEN", None) or "").strip()
    if not tok:
        return "none"
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()[-10:]


async def force_restore_driver_online_reply_keyboard(
    bot: Bot,
    chat_id: int,
    lang: str,
    *,
    context: str = "",
    order_id: Optional[int] = None,
    order_status: Optional[str] = None,
    request_path: Optional[str] = None,
) -> None:
    """
    Avval ReplyKeyboardRemove, keyin to‘liq online klaviatura.
    Idempotent: xavfsiz takroriy chaqirish (busy yoki to‘liq klaviatura holatida).
    """
    token_fp = _bot_token_fingerprint()
    full_kb = driver_keyboard_online_with_taximeter(lang)
    row_labels: list[list[str]] = [
        [getattr(b, "text", "") for b in row] for row in (full_kb.keyboard or [])
    ]

    logger.info(
        "driver_reply_kb: ENTRY chat_id=%s lang=%s context=%s order_id=%s order_status=%s "
        "request_path=%s bot_token_sha256_suffix=%s full_kb_rows=%s",
        chat_id,
        lang,
        context or "-",
        order_id,
        order_status or "-",
        request_path or "-",
        token_fp,
        row_labels,
    )

    logger.info(
        "driver_reply_kb: BEFORE ReplyKeyboardRemove chat_id=%s context=%s",
        chat_id,
        context or "-",
    )
    try:
        m_remove = await bot.send_message(
            chat_id, _KB_PLACEHOLDER, reply_markup=ReplyKeyboardRemove()
        )
        logger.info(
            "driver_reply_kb: AFTER ReplyKeyboardRemove chat_id=%s context=%s message_id=%s",
            chat_id,
            context or "-",
            getattr(m_remove, "message_id", None),
        )
    except Exception as e:
        logger.error(
            "driver_reply_kb: ReplyKeyboardRemove FAILED chat_id=%s context=%s err=%s\n%s",
            chat_id,
            context or "-",
            e,
            traceback.format_exc(),
        )
        raise

    logger.info(
        "driver_reply_kb: BEFORE full keyboard send chat_id=%s context=%s",
        chat_id,
        context or "-",
    )
    try:
        m_full = await bot.send_message(chat_id, "🟢", reply_markup=full_kb)
        logger.info(
            "driver_reply_kb: AFTER full keyboard send chat_id=%s context=%s message_id=%s",
            chat_id,
            context or "-",
            getattr(m_full, "message_id", None),
        )
    except Exception as e:
        logger.error(
            "driver_reply_kb: full keyboard send FAILED chat_id=%s context=%s err=%s\n%s",
            chat_id,
            context or "-",
            e,
            traceback.format_exc(),
        )
        raise
