"""Mijoz asosiy ReplyKeyboard — haydovchi bo'lish tugmasi yo'q (/driver orqali)."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.messages import get_text


def get_main_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Taksi, buyurtmalar, ma'lumot. Haydovchi ro'yxati: /driver."""
    t = lambda k: get_text(lang, k)
    buttons = [
        [KeyboardButton(text=t("btn_order"))],
        [KeyboardButton(text=t("btn_orders"))],
        [KeyboardButton(text=t("btn_info"))],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
