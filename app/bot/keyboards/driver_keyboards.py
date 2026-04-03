"""Haydovchi paneli klaviaturalari."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.messages import get_text

DRIVER_GROUP_INVITE_URL = "https://t.me/+7ynDXrgnrIw5Y2Qy"
# Eski importlar uchun (F.text filtrlari messages.da DRIVER_GROUP_TEXTS)
DRIVER_GROUP_BUTTON_TEXT = "👥 Guruhga qo'shilish"


def driver_keyboard_full(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Asosiy haydovchi paneli."""
    t = lambda k: get_text(lang, k)
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("driver_btn_online")),
                KeyboardButton(text=t("driver_btn_offline")),
            ],
            [KeyboardButton(text=t("driver_btn_link_card"))],
            [
                KeyboardButton(text=t("driver_btn_group")),
                KeyboardButton(text=t("driver_btn_balance")),
            ],
        ],
        resize_keyboard=True,
    )


def driver_keyboard_already_registered(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Allaqachon haydovchi bo'lgan foydalanuvchi."""
    return driver_keyboard_full(lang)


def driver_keyboard_pending_approval(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Ariza yuborilgandan keyin (tasdiq kutilmoqda)."""
    t = lambda k: get_text(lang, k)
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("driver_btn_online")),
                KeyboardButton(text=t("driver_btn_offline")),
            ],
            [KeyboardButton(text=t("driver_btn_group"))],
        ],
        resize_keyboard=True,
    )


def driver_keyboard_online_session(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Faqat ONLINE sessiyasida (Offline)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text(lang, "driver_btn_offline"))]],
        resize_keyboard=True,
    )
