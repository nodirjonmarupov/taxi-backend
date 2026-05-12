"""
Driver Handlers - To'liq funksional + Taximeter + Payme
"""
import asyncio
import json
import time
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis, get_trip_state, delete_trip_state
from app.crud.user import UserCRUD, DriverCRUD
from app.models.user import UserRole
from app.schemas.user import UserCreate
from app.models.order import Order, OrderStatus, order_skip_customer_notifications
from app.core.logger import get_logger
from app.core.config import settings
from app.utils.distance import haversine_distance
from sqlalchemy import text, select, update
from sqlalchemy.exc import IntegrityError
from app.services.taximeter_service import accumulate_order_distance_for_driver
from app.bot.keyboards.driver_keyboards import (
    DRIVER_GROUP_INVITE_URL,
    driver_keyboard_already_registered,
    driver_keyboard_full,
    driver_keyboard_online_busy,
    driver_keyboard_online_with_taximeter,
    driver_keyboard_pending_approval,
)
from app.bot.messages import (
    get_text,
    normalize_bot_lang,
    DRIVER_REG_BUTTON_TEXTS,
    DRIVER_ONLINE_TEXTS,
    DRIVER_OFFLINE_TEXTS,
    DRIVER_LINK_CARD_TEXTS,
    DRIVER_BALANCE_TEXTS,
    DRIVER_GROUP_TEXTS,
    DRIVER_OPEN_TAXIMETER_TEXTS,
)
from app.bot.lang_utils import db_lang_for_telegram
from app.utils.phone import normalize_phone

logger = get_logger(__name__)

driver_router = Router()


def driver_taximeter_reply_markup(
    driver_ui_lang: str,
    order_id: int,
    driver_id: int,
    *,
    with_chat: bool = False,
) -> InlineKeyboardMarkup:
    """Taksometr WebApp tugmasi (accept va qo'lda ochish uchun bir xil URL/token)."""
    from app.utils.webapp_token import generate_webapp_token

    base_url = getattr(settings, "WEBAPP_BASE_URL", "https://candid-semiexposed-dung.ngrok-free.dev")
    ts = int(time.time())
    token = generate_webapp_token(order_id, driver_id)
    webapp_url = f"{base_url}/taximeter_v2?order_id={order_id}&token={token}&t={ts}&v={ts}"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=get_text(driver_ui_lang, "driver_btn_open_taximeter"),
                web_app=WebAppInfo(url=webapp_url),
            )
        ],
    ]
    if with_chat:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text(driver_ui_lang, "driver_btn_write_customer"),
                    callback_data="driver_chat_tip",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _notify_customer_driver_assigned(
    bot,
    db,
    *,
    order: Order,
    driver,
    driver_user,
) -> None:
    """Haydovchi biriktirilgach mijozga xabar (xarita/kuzatish tugmasisiz)."""
    if order_skip_customer_notifications(order):
        return
    order_user = await UserCRUD.get_by_id(db, order.user_id)
    if not order_user:
        return
    if getattr(order, "user_tracking_message_id", None):
        return
    try:
        user_lang = normalize_bot_lang(getattr(order_user, "language_code", None) or "uz")
        driver_msg = (
            f"{get_text(user_lang, 'driver_found_title')}\n\n"
            f"👨‍✈️ {driver_user.first_name}\n"
            f"🚗 {driver.car_model} ({driver.car_number})\n"
            f"📞 Haydovchi: {getattr(driver_user, 'phone', None) or 'N/A'}\n"
            f"⭐️ {get_text(user_lang, 'rating_label')}: {driver.rating:.1f}/5.0\n\n"
            f"{get_text(user_lang, 'taxi_arriving')}\n"
            f"{get_text(user_lang, 'chat_via_bot')}"
        )
        await bot.send_message(
            chat_id=order_user.telegram_id,
            text=driver_msg,
            parse_mode="HTML",
        )
        logger.info("✅ Mijozga xabar yuborildi (order=%s)", order.id)
    except Exception as e:
        logger.error(f"❌ Mijozga xabar yuborishda xato: {e}")


async def _manual_order_customer_user_id(db, driver_user_id: int) -> int:
    """Manual buyurtma uchun mijoz users.id — haydovchi hisobi emas (Order.user_id FK)."""
    env_uid = getattr(settings, "MANUAL_TRIP_CUSTOMER_USER_ID", None)
    if env_uid is not None:
        uid = int(env_uid)
        u = await UserCRUD.get_by_id(db, uid)
        if not u:
            raise ValueError("manual_customer_user_missing")
        if uid == driver_user_id:
            raise ValueError("manual_customer_is_driver")
        return uid

    fixed_tg = int(getattr(settings, "MANUAL_TRIP_CUSTOMER_TELEGRAM_ID", -910001001002))
    row = await UserCRUD.get_by_telegram_id(db, fixed_tg)
    if row:
        if row.id == driver_user_id:
            raise ValueError("manual_customer_is_driver")
        return row.id

    try:
        created = await UserCRUD.create(
            db,
            UserCreate(telegram_id=fixed_tg, first_name="Manual", role=UserRole.USER),
        )
        if created.id == driver_user_id:
            raise ValueError("manual_customer_is_driver")
        return created.id
    except IntegrityError:
        await db.rollback()
        row2 = await UserCRUD.get_by_telegram_id(db, fixed_tg)
        if not row2:
            raise
        if row2.id == driver_user_id:
            raise ValueError("manual_customer_is_driver")
        return row2.id


def is_web_active(driver_id: int) -> bool:
    """WebApp GPS hozir ustun (Redis web_active kaliti)."""
    try:
        r = get_redis()
        if not r:
            return False
        return bool(r.get(f"web_active:{driver_id}"))
    except Exception as e:
        logger.warning(f"web_active check failed: {e}")
        return False

# Live location optimization cache
_last_saved_location: dict = {}  # {driver_id: (lat, lng, timestamp)}
MIN_MOVE_METERS = 50    # min movement to trigger DB save
MIN_SAVE_INTERVAL = 30  # min seconds between saves


# ============================================
# FSM STATES
# ============================================

class DriverStates(StatesGroup):
    """Driver ro'yxatdan o'tish holatlari"""
    waiting_for_phone = State()
    waiting_for_car_number = State()
    waiting_for_car_model = State()
    waiting_for_car_color = State()
    waiting_for_license = State()
    waiting_for_license_photo = State()
    waiting_for_manual_confirm = State()


class PaymeStates(StatesGroup):
    """Payme karta bog'lash holatlari"""
    waiting_for_card = State()
    waiting_for_expire = State()
    waiting_for_sms = State()


# ============================================
# WEBAPP DATA (Taksometrdan safar yakunlashi)
# ============================================

@driver_router.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    """Taksometr WebApp sendData - faqat log. Xabarlar API orqali yuboriladi (update_order_status)."""
    try:
        data_str = message.web_app_data.data if message.web_app_data else None
        if not data_str:
            return
        data = json.loads(data_str)
        if data.get("status") == "finished" and data.get("order_id"):
            logger.info(f"📱 WebApp sendData: Safar #{data.get('order_id')} yakunlandi (xabarlar API orqali yuboriladi)")
    except Exception as e:
        logger.error(f"WebApp data handler xato: {e}")


# ============================================
# DRIVER MENU
# ============================================

@driver_router.message(Command("driver"))
async def driver_menu(message: Message, lang: str = "uz"):
    """Haydovchi asosiy menyusi"""
    lang = "uz"
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            
            if not user:
                await message.answer(
                    get_text(lang, "driver_err_start_first"),
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
            
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            
            if not driver:
                keyboard = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text=get_text(lang, "btn_be_driver"))]],
                    resize_keyboard=True
                )
                await message.answer(
                    get_text(lang, "driver_not_registered_prompt"),
                    reply_markup=keyboard
                )
                return
            
            if not getattr(driver, "is_active", True):
                await message.answer(
                    get_text(lang, "driver_blocked_full"),
                    parse_mode="HTML",
                    reply_markup=ReplyKeyboardMarkup(
                        keyboard=[[KeyboardButton(text=get_text(lang, "btn_order"))]],
                        resize_keyboard=True
                    )
                )
                return
            
            # STATUS
            status = "🟢 ONLINE" if driver.is_available else "🔴 OFFLINE"
            warning = ""
            stars_count = int(driver.rating) if driver.rating else 5
            stars_display = "⭐" * stars_count
            
            await message.answer(
                get_text(
                    lang,
                    "driver_panel_body",
                    name=user.first_name or "",
                    car_model=driver.car_model,
                    car_number=driver.car_number,
                    rating=f"{driver.rating:.1f}",
                    stars=stars_display,
                    trips=driver.total_trips or 0,
                    balance=f"{float(driver.balance or 0):.0f}",
                    earnings=f"{driver.total_earnings or 0:.0f}",
                    status=status,
                    warning=warning,
                ),
                reply_markup=driver_keyboard_full(lang),
                parse_mode="HTML",
            )
            
    except Exception as e:
        logger.error(f"❌ Driver menu xato: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await message.answer(get_text(lang, "driver_err_generic_retry"))


@driver_router.message(F.text.in_(DRIVER_GROUP_TEXTS))
async def driver_open_group_invite(message: Message, lang: str = "uz"):
    """Reply klaviaturadagi guruh tugmasi — havola yuboriladi."""
    lang = "uz"
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            if not user:
                await message.answer(get_text(lang, "driver_err_start_first"))
                return
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            if not driver:
                await message.answer(get_text(lang, "driver_err_group_only_drivers"))
                return
        await message.answer(
            get_text(lang, "driver_group_invite_html", url=DRIVER_GROUP_INVITE_URL),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Guruh havolasi xato: {e}")
        await message.answer(get_text(lang, "driver_err_generic_short"))


# ============================================
# DRIVER REGISTRATION
# ============================================

@driver_router.message(Command("driver_reg"))
@driver_router.message(F.text.in_(DRIVER_REG_BUTTON_TEXTS))
async def register_driver_start(message: Message, state: FSMContext, lang: str = "uz"):
    """Ro'yxatdan o'tishni boshlash"""
    lang = "uz"
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            
            if user:
                driver = await DriverCRUD.get_by_user_id(db, user.id)
                
                if driver:
                    await message.answer(
                        get_text(
                            lang,
                            "driver_already_registered_warn",
                            car_model=driver.car_model,
                            car_number=driver.car_number,
                        ),
                        reply_markup=driver_keyboard_already_registered(lang),
                        parse_mode="HTML",
                    )
                    return
        
        await message.answer(
            get_text(lang, "driver_reg_phone_prompt"),
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=get_text(lang, "driver_btn_send_phone"), request_contact=True)]],
                resize_keyboard=True
            ),
            parse_mode="HTML"
        )
        await state.set_state(DriverStates.waiting_for_phone)
        
    except Exception as e:
        logger.error(f"❌ Register start xato: {e}")
        await message.answer(get_text(lang, "driver_err_generic_retry"))


# Inline tanlash uchun variantlar
CAR_MODELS = [
    ["Cobalt", "Gentra", "Nexia 3"],
    ["Malibu", "Lacetti", "Spark"],
    ["Damas", "Tico", "Matiz"],
    ["Boshqa"]
]
CAR_COLORS = [
    ["Oq", "Qora", "Kumush"],
    ["Kulrang", "Ko'k", "Yashil"],
    ["Qizil", "Sariq", "Boshqa"]
]


@driver_router.message(DriverStates.waiting_for_phone, F.contact)
async def register_phone(message: Message, state: FSMContext, lang: str = "uz"):
    """Telefon qabul qilish (request_contact)"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    await state.update_data(phone=message.contact.phone_number)
    await message.answer(
        get_text(lang, "driver_phone_ok_next_plate"),
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(DriverStates.waiting_for_car_number)


@driver_router.message(DriverStates.waiting_for_phone)
async def register_phone_invalid(message: Message, state: FSMContext, lang: str = "uz"):
    """Telefon o'rniga boshqa yuborilganda"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    await message.answer(
        get_text(lang, "driver_phone_use_button"),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text(lang, "driver_btn_send_phone"), request_contact=True)]],
            resize_keyboard=True
        ),
        parse_mode="HTML"
    )


@driver_router.message(DriverStates.waiting_for_car_number, F.text)
async def register_car_number(message: Message, state: FSMContext, lang: str = "uz"):
    """Mashina raqami"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    await state.update_data(car_number=message.text.strip().upper())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m, callback_data=f"car_model:{m}") for m in row]
        for row in CAR_MODELS
    ])
    await message.answer(get_text(lang, "driver_car_accept_model"), reply_markup=kb)
    await state.set_state(DriverStates.waiting_for_car_model)


@driver_router.callback_query(StateFilter(DriverStates.waiting_for_car_model), F.data.startswith("car_model:"))
async def register_car_model(callback: CallbackQuery, state: FSMContext, lang: str = "uz"):
    """Mashina modeli (inline tanlash)"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, callback.from_user.id)
    model = callback.data.split(":")[1]
    await state.update_data(car_model=model)
    await callback.answer(get_text(lang, "driver_cb_accept_ok"))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"car_color:{c}") for c in row]
        for row in CAR_COLORS
    ])
    await callback.message.edit_text(get_text(lang, "driver_pick_car_color"), reply_markup=kb)
    await state.set_state(DriverStates.waiting_for_car_color)


@driver_router.callback_query(StateFilter(DriverStates.waiting_for_car_color), F.data.startswith("car_color:"))
async def register_car_color(callback: CallbackQuery, state: FSMContext, lang: str = "uz"):
    """Mashina rangi (inline tanlash)"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, callback.from_user.id)
    color = callback.data.split(":")[1]
    await state.update_data(car_color=color)
    await callback.answer(get_text(lang, "driver_cb_accept_ok"))
    await callback.message.edit_text(get_text(lang, "driver_license_prompt"))
    await state.set_state(DriverStates.waiting_for_license)


@driver_router.message(DriverStates.waiting_for_license, F.text)
async def register_license(message: Message, state: FSMContext, lang: str = "uz"):
    """
    Guvohnoma raqami qabul qilish.
    Vaqtinchalik guvohnoma rasm talab qilinmaydi – shu yerning o'zida driver yaratiladi.
    """
    lang = "uz"
    await state.update_data(license_number=message.text.strip())
    data = await state.get_data()
    file_id = None  # vaqtinchalik rasm olmaymiz

    try:
        async with AsyncSessionLocal() as db:
            from app.models.user import Driver as DriverModel
            from app.core.config import settings

            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)

            if not user:
                await message.answer(get_text(lang, "driver_err_user_missing"))
                await state.clear()
                return

            driver = await DriverCRUD.get_by_user_id(db, user.id)

            if driver:
                await message.answer(get_text(lang, "driver_err_already_driver_cmd"))
                await state.clear()
                return

            new_driver = DriverModel(
                user_id=user.id,
                car_number=data.get('car_number'),
                car_model=data.get('car_model'),
                car_color=data.get('car_color'),
                license_number=data.get('license_number'),
                driver_license_photo_id=file_id,
                is_verified=False,
                is_available=False,
                rating=5.0,
                total_trips=0,
                completed_trips=0,
                cancelled_trips=0,
                total_earnings=0.0,
            )
            db.add(new_driver)
            user.role = UserRole.DRIVER
            _raw_phone = data.get('phone')
            try:
                _p = normalize_phone(_raw_phone)
            except Exception:
                _p = None
            if not _p:
                raise ValueError("Invalid phone number")
            if _p:
                user.phone = _p
                new_driver.phone_e164 = _p

            await db.commit()
            await db.refresh(new_driver)
            await state.clear()

            await message.answer(
                get_text(lang, "driver_app_submitted"),
                reply_markup=driver_keyboard_pending_approval(lang),
                parse_mode="HTML",
            )

            logger.info(f"✅ Driver arizasi yuborildi (rasmsiz): User {user.telegram_id}, Driver {new_driver.id}")

            admin_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_driver:{new_driver.id}"),
                    InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_driver:{new_driver.id}")
                ]
            ])

            admin_text = (
                "🚕 <b>YANGI HAYDOVCHI ARIZASI</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Ism:</b> {user.first_name} {user.last_name or ''}\n"
                f"📱 <b>Telefon:</b> {user.phone or 'N/A'}\n"
                f"📞 <b>Telegram:</b> @{user.username or 'yoq'}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🚗 <b>Mashina:</b> {data.get('car_model')} ({data.get('car_number')})\n"
                f"🎨 <b>Rang:</b> {data.get('car_color')}\n"
                f"📄 <b>Guvohnoma:</b> {data.get('license_number')}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 {new_driver.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                "📸 <i>Guvohnoma rasmi yuborilmagan (vaqtinchalik rasm talab qilinmaydi).</i>"
            )

            from app.bot.telegram_bot import bot
            for admin_id in getattr(settings, "ADMIN_IDS", []):
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=admin_kb,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Admin {admin_id}ga xabar yuborishda xato: {e}")

    except Exception as e:
        logger.error(f"❌ Driver yaratishda xato: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer(get_text(lang, "driver_save_failed"))
        await state.clear()


@driver_router.message(DriverStates.waiting_for_license_photo, F.photo)
async def register_license_photo(message: Message, state: FSMContext, lang: str = "uz"):
    """Guvohnoma rasmini qabul qilish va admin'ga yuborish"""
    lang = "uz"
    data = await state.get_data()
    photo = message.photo[-1]
    file_id = photo.file_id

    try:
        async with AsyncSessionLocal() as db:
            from app.models.user import Driver as DriverModel
            from app.core.config import settings

            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)

            if not user:
                await message.answer(get_text(lang, "driver_err_user_missing"))
                await state.clear()
                return

            driver = await DriverCRUD.get_by_user_id(db, user.id)

            if driver:
                await message.answer(get_text(lang, "driver_err_already_driver_cmd"))
                await state.clear()
                return

            new_driver = DriverModel(
                user_id=user.id,
                car_number=data.get('car_number'),
                car_model=data.get('car_model'),
                car_color=data.get('car_color'),
                license_number=data.get('license_number'),
                driver_license_photo_id=file_id,
                is_verified=False,
                is_available=False,
                rating=5.0,
                total_trips=0,
                total_earnings=0.0,
            )
            db.add(new_driver)
            user.role = UserRole.DRIVER
            user.phone = data.get('phone')

            await db.commit()
            await db.refresh(new_driver)
            await state.clear()

            await message.answer(
                get_text(lang, "driver_app_submitted"),
                reply_markup=driver_keyboard_pending_approval(lang),
                parse_mode="HTML",
            )

            logger.info(f"✅ Driver arizasi yuborildi: User {user.telegram_id}, Driver {new_driver.id}")

            admin_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_driver:{new_driver.id}"),
                    InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_driver:{new_driver.id}")
                ]
            ])

            admin_text = (
                "🚕 <b>YANGI HAYDOVCHI ARIZASI</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Ism:</b> {user.first_name} {user.last_name or ''}\n"
                f"📱 <b>Telefon:</b> {user.phone or 'N/A'}\n"
                f"📞 <b>Telegram:</b> @{user.username or 'yoq'}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🚗 <b>Mashina:</b> {data.get('car_model')} ({data.get('car_number')})\n"
                f"🎨 <b>Rang:</b> {data.get('car_color')}\n"
                f"📄 <b>Guvohnoma:</b> {data.get('license_number')}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📅 {new_driver.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                "📸 <i>Guvohnoma rasmi pastda:</i>"
            )

            from app.bot.telegram_bot import bot
            for admin_id in getattr(settings, "ADMIN_IDS", []):
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=admin_kb,
                        parse_mode="HTML"
                    )
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=file_id,
                        caption="📄 Haydovchilik guvohnomasi"
                    )
                except Exception as e:
                    logger.error(f"Admin {admin_id}ga xabar yuborishda xato: {e}")

    except Exception as e:
        logger.error(f"❌ Driver yaratishda xato: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer(get_text(lang, "driver_save_failed"))
        await state.clear()


@driver_router.message(DriverStates.waiting_for_license_photo)
async def register_license_photo_invalid(message: Message, state: FSMContext, lang: str = "uz"):
    """Rasm o'rniga matn/document yuborilganda - validatsiya"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    await message.answer(
        get_text(lang, "driver_photo_license_only"),
        parse_mode="HTML"
    )


# ============================================
# ACCEPT ORDER + TAXIMETER
# ============================================

@driver_router.callback_query(F.data.startswith("accept_order:"))
async def accept_order(callback: CallbackQuery):
    """Buyurtmani qabul qilish va TAKSOMETR yuborish"""
    try:
        order_id = int(callback.data.split(":")[1])
        # Acknowledge Telegram immediately to prevent callback retry (2s, 7s retries)
        await callback.answer()
        from app.services.order_service import stop_driver_timer, clear_dispatch_state

        logger.info(f"🎯 Driver {callback.from_user.id} buyurtma {order_id}ni qabul qilmoqda...")
        
        async with AsyncSessionLocal() as db:
            try:
                user = await UserCRUD.get_by_telegram_id(db, callback.from_user.id)
                driver_ui_lang = normalize_bot_lang(getattr(user, "language_code", None) or "uz") if user else "uz"
                if not user:
                    await callback.message.answer(get_text("uz", "driver_accept_err"))
                    return

                driver = await DriverCRUD.get_by_user_id(db, user.id)
                if not driver:
                    await callback.message.answer(get_text(driver_ui_lang, "driver_accept_err"))
                    return
                if not getattr(driver, "is_active", True):
                    await callback.message.answer(get_text(driver_ui_lang, "driver_accept_deactivated"))
                    return

                from app.crud.order_crud import OrderCRUD

                order = await OrderCRUD.get_by_id_for_update(db, order_id)

                if not order:
                    await callback.message.answer(get_text(driver_ui_lang, "driver_accept_order_missing"))
                    return

                if order.status != OrderStatus.PENDING:
                    await callback.message.answer(get_text(driver_ui_lang, "driver_accept_order_taken"))
                    return

                existing = await OrderCRUD.get_ongoing_order_for_driver(db, driver.id)
                if existing and existing.id != order_id:
                    await callback.message.answer(get_text(driver_ui_lang, "driver_accept_busy"))
                    return

                # Now safe to stop timer and clear dispatch — order is being accepted
                stop_driver_timer(order_id)
                clear_dispatch_state(order_id)

                order.driver_id = driver.id
                order.status = OrderStatus.ACCEPTED
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
                raise
            
            logger.info(f"✅ Order {order_id} status: ACCEPTED")
            kb = driver_taximeter_reply_markup(driver_ui_lang, order.id, driver.id, with_chat=True)
            logger.info(f"📱 Taximeter WebApp tugmasi order_id={order.id}")

            order_customer = await UserCRUD.get_by_id(db, order.user_id)
            cust_phone = (
                (getattr(order_customer, "phone", None) or "").strip()
                if order_customer
                else ""
            ) or "N/A"
            accept_body = get_text(driver_ui_lang, "driver_accept_order_body", order_id=order.id)
            oid_marker = f"#{order.id}"
            _lines_out: list[str] = []
            _phone_inserted = False
            for _ln in accept_body.split("\n"):
                _lines_out.append(_ln)
                if not _phone_inserted and _ln.startswith("📍") and oid_marker in _ln:
                    _lines_out.append(f"📞 Mijoz: {cust_phone}")
                    _phone_inserted = True
            accept_text = "\n".join(_lines_out)

            # Always send a NEW message with taximeter button — never rely on edit_text
            # edit_text may have been modified by timer, driver may not see old message
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                accept_text,
                reply_markup=kb,
                parse_mode="HTML",
            )

            # Hide manual taximeter from bottom keyboard while driver has an active order.
            # The order-specific inline taximeter button (sent above) is the correct entry point.
            await callback.message.answer(
                "🚖",
                reply_markup=driver_keyboard_online_busy(driver_ui_lang),
            )

            logger.info(f"✅ Driver {driver.id} buyurtma {order_id}ni qabul qildi")

            await _notify_customer_driver_assigned(
                callback.bot, db, order=order, driver=driver, driver_user=user
            )

    except Exception as e:
        logger.error(f"❌ Qabul qilishda xato: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await callback.answer(get_text("uz", "driver_accept_fatal"), show_alert=True)


@driver_router.callback_query(F.data == "driver_chat_tip")
async def driver_chat_tip(callback: CallbackQuery):
    """Mijozga yozish eslatmasi — ko'zga tashlanadigan alert."""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, callback.from_user.id)
    await callback.answer(get_text(lang, "driver_chat_tip_alert"), show_alert=True)


@driver_router.callback_query(F.data.startswith("reject_order:"))
async def reject_order(callback: CallbackQuery):
    """Buyurtmani rad etish — keyingi haydovchiga taklif yuborish"""
    try:
        order_id = int(callback.data.split(":")[1])
        from app.services.order_service import offer_to_next_driver
        driver_lang = "uz"
        try:
            async with AsyncSessionLocal() as _db:
                driver_lang = await db_lang_for_telegram(_db, callback.from_user.id)
        except Exception:
            pass
        await callback.message.edit_text(
            get_text(driver_lang, "order_rejected"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
        )
        await callback.answer(get_text(driver_lang, "driver_reject_ok_toast"))
        logger.info(f"Driver {callback.from_user.id} buyurtma {order_id}ni rad etdi")
        asyncio.create_task(offer_to_next_driver(order_id, from_timeout_or_reject=True))
    except Exception as e:
        logger.error(f"❌ Rad etishda xato: {e}")
        await callback.answer(get_text("uz", "driver_accept_err"), show_alert=True)


# ============================================
# ONLINE/OFFLINE
# ============================================

# Track online drivers for location refresh
_online_drivers = set()


async def _keep_location_fresh(driver_id: int):
    """Driver online bo'lganda location_updated_at ni yangilab turadi"""
    _online_drivers.add(driver_id)
    try:
        while driver_id in _online_drivers:
            await asyncio.sleep(60)
            if driver_id not in _online_drivers:
                break
            try:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        text("""
                            UPDATE drivers
                            SET location_updated_at = NOW()
                            WHERE id = :driver_id
                            AND is_available = true
                            AND location IS NOT NULL
                        """),
                        {"driver_id": driver_id}
                    )
                    await db.commit()
                    if result.rowcount > 0:
                        pass  # silent refresh
                    else:
                        # Driver offline bo'ldi
                        _online_drivers.discard(driver_id)
                        break
            except Exception:
                pass
    finally:
        _online_drivers.discard(driver_id)


@driver_router.message(F.text.in_(DRIVER_ONLINE_TEXTS))
async def go_online(message: Message, lang: str = "uz"):
    """Online bo'lish"""
    lang = "uz"
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            
            if not user:
                logger.error(f"User topilmadi: {message.from_user.id}")
                await message.answer(get_text(lang, "driver_go_online_err_start"))
                return
            
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            
            if not driver:
                logger.error(f"Driver topilmadi: user_id={user.id}")
                await message.answer(get_text(lang, "driver_go_online_not_driver"))
                return
            if not getattr(driver, "is_active", True):
                await message.answer(get_text(lang, "driver_blocked_panel"))
                return

            # Vaqt: PostgreSQL NOW() — matching so'rovidagi NOW() bilan sinxron
            if driver.current_latitude and driver.current_longitude:
                await db.execute(
                    text("""
                        UPDATE drivers SET
                            is_available = true,
                            status = 'active',
                            location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                            location_updated_at = NOW()
                        WHERE id = :driver_id
                    """),
                    {
                        "driver_id": driver.id,
                        "lon": float(driver.current_longitude),
                        "lat": float(driver.current_latitude),
                    },
                )
            else:
                await db.execute(
                    text("""
                        UPDATE drivers SET
                            is_available = true,
                            status = 'active',
                            location_updated_at = NOW()
                        WHERE id = :driver_id
                    """),
                    {"driver_id": driver.id},
                )

            await db.commit()

            asyncio.create_task(_keep_location_fresh(driver.id))

            logger.info(f"✅ Driver {driver.id} ONLINE bo'ldi")

            await message.answer_photo(
                photo="AgACAgIAAxkBAAICpWnKHSfqZLUxRjRJzimH2Xke1IAQAAJGFWsbsUlRSg5AuNQWgBKyAQADAgADeAADOgQ",
                caption=(
                    "✅ <b>Siz ONLINE holatdasiz.</b>\n\n"
                    "📍 <b>Jonli lokatsiya yuborish:</b>\n"
                    "📎 (Biriktirish) → Joylashuv → "
                    "Jonli joylashuvimni ulashish → 8 soat\n\n"
                    "⚡ Shunday qilib buyurtmalar avtomatik keladi!"
                ),
                parse_mode="HTML",
                reply_markup=driver_keyboard_online_with_taximeter(lang),
            )
            
    except Exception as e:
        logger.error(f"❌ Online qilishda xato: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await message.answer(get_text(lang, "driver_err_generic_retry"))


@driver_router.message(F.text.in_(DRIVER_OFFLINE_TEXTS))
async def go_offline(message: Message, lang: str = "uz"):
    """Offline bo'lish"""
    lang = "uz"
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            
            if not user:
                logger.error(f"User topilmadi: {message.from_user.id}")
                await message.answer(get_text(lang, "driver_go_online_err_start"))
                return
            
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            
            if not driver:
                logger.error(f"Driver topilmadi: user_id={user.id}")
                await message.answer(get_text(lang, "driver_go_online_not_driver"))
                return
            if not getattr(driver, "is_active", True):
                await message.answer(get_text(lang, "driver_blocked_short"))
                return

            _online_drivers.discard(driver.id)
            _last_saved_location.pop(driver.id, None)

            driver.is_available = False
            driver.status = "pending"
            await db.commit()

            logger.info(f"Driver {driver.id} OFFLINE bo'ldi")
            
            await message.answer(
                get_text(lang, "driver_offline_intro"),
                reply_markup=driver_keyboard_full(lang),
                parse_mode="HTML",
            )
            
    except Exception as e:
        logger.error(f"❌ Offline qilishda xato: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await message.answer(get_text(lang, "driver_err_generic_retry"))


@driver_router.message(F.text.in_(DRIVER_OPEN_TAXIMETER_TEXTS))
async def open_taximeter_manual(message: Message, state: FSMContext):
    """Haydovchi panelidan: qo'lda safarni boshlashdan oldin tasdiqlash so'raladi."""
    lang = "uz"
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            driver_ui_lang = (
                normalize_bot_lang(getattr(user, "language_code", None) or "uz") if user else "uz"
            )
            if not user:
                await message.answer(get_text(lang, "driver_go_online_err_start"))
                return
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            if not driver:
                await message.answer(get_text(lang, "driver_go_online_not_driver"))
                return
            if not getattr(driver, "is_active", True):
                await message.answer(get_text(lang, "driver_blocked_panel"))
                return

            from app.crud.order_crud import OrderCRUD

            ongoing = await OrderCRUD.get_ongoing_order_for_driver(db, driver.id)
            if ongoing:
                cur = (ongoing.status.value if hasattr(ongoing.status, "value") else ongoing.status) or ""
                cur_l = str(cur).lower()
                if cur_l in ("accepted", "in_progress"):
                    r_ongoing = get_redis()
                    if r_ongoing and cur_l == "in_progress":
                        from app.api.routes.webapp import _ensure_trip_state_for_order_start

                        await _ensure_trip_state_for_order_start(
                            r_ongoing, ongoing.id, driver.id, db
                        )
                    drv_sync = await DriverCRUD.get_by_id(db, driver.id)
                    if drv_sync and cur_l == "in_progress":
                        drv_sync.is_available = False
                        await db.commit()
                    kb = driver_taximeter_reply_markup(
                        driver_ui_lang, ongoing.id, driver.id, with_chat=(cur_l == "accepted")
                    )
                    await message.answer(
                        get_text(driver_ui_lang, "driver_manual_taximeter_active", order_id=ongoing.id),
                        reply_markup=kb,
                        parse_mode="HTML",
                    )
                return

        # Race-condition guard: if confirmation is already pending, ignore repeated taps
        current_state = await state.get_state()
        if current_state == DriverStates.waiting_for_manual_confirm.state:
            return

        # Show confirmation inline keyboard — do NOT start trip yet
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Boshlash", callback_data="manual_trip_confirm:yes"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manual_trip_confirm:no"),
            ]
        ])
        await message.answer(
            "Haqiqatan ham manual safarni boshlamoqchimisiz?",
            reply_markup=confirm_kb,
        )
        await state.set_state(DriverStates.waiting_for_manual_confirm)

    except Exception as e:
        logger.error(f"open_taximeter_manual: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer(get_text(lang, "driver_err_generic_retry"))


@driver_router.callback_query(
    F.data == "manual_trip_confirm:no",
    StateFilter(DriverStates.waiting_for_manual_confirm),
)
async def manual_trip_cancel(callback: CallbackQuery, state: FSMContext):
    """Manual safar bekor qilindi — hech narsa yaratilmaydi."""
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


@driver_router.callback_query(
    F.data == "manual_trip_confirm:yes",
    StateFilter(DriverStates.waiting_for_manual_confirm),
)
async def manual_trip_start_confirmed(callback: CallbackQuery, state: FSMContext):
    """Manual safar tasdiqlandi — order yaratish va taksometrni ishga tushirish."""
    # Clear state immediately to prevent double-tap race
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

    lang = "uz"
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, callback.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, callback.from_user.id)
            driver_ui_lang = (
                normalize_bot_lang(getattr(user, "language_code", None) or "uz") if user else "uz"
            )
            if not user:
                await callback.message.answer(get_text(lang, "driver_go_online_err_start"))
                return
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            if not driver:
                await callback.message.answer(get_text(lang, "driver_go_online_not_driver"))
                return

            from app.crud.order_crud import OrderCRUD

            # Double-check: no ongoing trip appeared between confirm and yes-tap
            ongoing = await OrderCRUD.get_ongoing_order_for_driver(db, driver.id)
            if ongoing:
                cur_l = str(
                    ongoing.status.value if hasattr(ongoing.status, "value") else ongoing.status
                ).lower()
                if cur_l in ("accepted", "in_progress"):
                    kb = driver_taximeter_reply_markup(
                        driver_ui_lang, ongoing.id, driver.id, with_chat=(cur_l == "accepted")
                    )
                    await callback.message.answer(
                        get_text(driver_ui_lang, "driver_manual_taximeter_active", order_id=ongoing.id),
                        reply_markup=kb,
                        parse_mode="HTML",
                    )
                return

            from app.api.routes.webapp import _ensure_trip_state_for_order_start
            from app.schemas.order import OrderCreate
            from app.services.pricing_service import PricingService
            from app.services.settings_service import get_settings, SettingsLoadError
            from app.services.taximeter_service import compute_fare

            try:
                cust_uid = await _manual_order_customer_user_id(db, driver.user_id)
            except ValueError as ve:
                logger.error("manual_trip_start_confirmed customer user: %s", ve)
                await callback.message.answer(get_text(lang, "driver_err_generic_retry"))
                return

            try:
                tariff = await get_settings(db)
            except SettingsLoadError:
                await callback.message.answer(get_text(lang, "driver_err_generic_retry"))
                return

            lat = getattr(driver, "current_latitude", None)
            lon = getattr(driver, "current_longitude", None)
            if lat is None or lon is None:
                lat, lon = 41.311081, 69.279737
            lat_f, lon_f = float(lat), float(lon)

            snap = PricingService.build_tariff_snapshot_from_settings(tariff)
            estimated_price = float(compute_fare(snap, 0.0, 0))

            oc = OrderCreate(
                pickup_latitude=lat_f,
                pickup_longitude=lon_f,
                pickup_address="Manual",
                destination_latitude=lat_f,
                destination_longitude=lon_f,
                estimated_price=estimated_price,
                distance_km=0.0,
            )
            new_order = await OrderCRUD.create(db, cust_uid, oc)
            await db.execute(
                update(Order).where(Order.id == new_order.id).values(source="manual")
            )
            await db.commit()
            await db.refresh(new_order)
            await OrderCRUD.update_status(db, new_order.id, OrderStatus.ACCEPTED, driver_id=driver.id)
            order_acc = await OrderCRUD.get_by_id(db, new_order.id)
            if order_acc:
                await _notify_customer_driver_assigned(
                    callback.bot, db, order=order_acc, driver=driver, driver_user=user
                )
            await OrderCRUD.update_status(
                db,
                new_order.id,
                OrderStatus.IN_PROGRESS,
                apply_taximeter_start=True,
                trip_start_lat=lat_f,
                trip_start_lon=lon_f,
            )
            r = get_redis()
            if r:
                await _ensure_trip_state_for_order_start(r, new_order.id, driver.id, db)

            drv_manual = await DriverCRUD.get_by_id(db, driver.id)
            if drv_manual:
                drv_manual.is_available = False
                await db.commit()

            kb = driver_taximeter_reply_markup(
                driver_ui_lang, new_order.id, driver.id, with_chat=False
            )
            await callback.message.answer(
                get_text(driver_ui_lang, "driver_manual_taximeter_ready", order_id=new_order.id),
                reply_markup=kb,
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"manual_trip_start_confirmed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await callback.message.answer(get_text(lang, "driver_err_generic_retry"))


# ============================================
# LOCATION UPDATE
# ============================================

@driver_router.message(F.location)
async def update_location(message: Message, lang: str = "uz"):
    """Lokatsiya yangilash"""
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            if not user:
                return
            
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            if not driver or not getattr(driver, "is_active", True):
                return

            if is_web_active(driver.id):
                return

            if not driver.is_available or driver.status != 'active':
                return

            lat = message.location.latitude
            lon = message.location.longitude

            if is_web_active(driver.id):
                return

            # PostGIS/Geography uchun location + location_updated_at ham yangilanadi
            if is_web_active(driver.id):
                return
            await db.execute(
                text("""
                    UPDATE drivers
                    SET
                        current_latitude = :lat,
                        current_longitude = :lon,
                        location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                        location_updated_at = NOW()
                    WHERE id = :driver_id
                """),
                {"driver_id": driver.id, "lat": lat, "lon": lon},
            )
            if is_web_active(driver.id):
                return
            await accumulate_order_distance_for_driver(db, driver.id, lat, lon)
            await db.commit()

            logger.debug(f"📍 Driver {driver.id} lokatsiya yangilandi: {lat:.6f}, {lon:.6f}")
            
            await message.answer(get_text(lang, "driver_location_ok"), parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"❌ Lokatsiya yangilashda xato: {e}")


# ============================================
# TELEGRAM LIVE LOCATION (edited_message)
# ============================================

@driver_router.edited_message(F.location)
async def live_location_update(message: Message):
    """Telegram Live Location avtomatik yangilanishi"""
    try:
        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(
                db, message.from_user.id
            )
            if not user:
                return

            driver = await DriverCRUD.get_by_user_id(db, user.id)
            if not driver:
                return

            if is_web_active(driver.id):
                return

            # Skip if driver is offline — save DB resources
            if not driver.is_available or driver.status != 'active':
                logger.debug(
                    f"⏭ Driver {driver.id} offline, "
                    f"live location skip qilindi"
                )
                return

            lat = message.location.latitude
            lon = message.location.longitude
            now = time.time()

            trip_row = await db.execute(
                select(Order.id)
                .where(Order.driver_id == driver.id)
                .where(Order.status == OrderStatus.IN_PROGRESS)
                .limit(1)
            )
            in_progress = trip_row.scalar_one_or_none() is not None

            if is_web_active(driver.id):
                return

            if in_progress:
                if is_web_active(driver.id):
                    return
                await db.execute(
                    text("""
                        UPDATE drivers
                        SET
                            current_latitude = :lat,
                            current_longitude = :lon,
                            location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                            location_updated_at = NOW()
                        WHERE id = :driver_id
                    """),
                    {"driver_id": driver.id, "lat": lat, "lon": lon},
                )
                if is_web_active(driver.id):
                    return
                await accumulate_order_distance_for_driver(db, driver.id, lat, lon)
                await db.commit()
                logger.debug(
                    f"📍 Driver {driver.id} safar live location: {lat:.6f}, {lon:.6f}"
                )
                return

            # FIX 1: Skip if driver not moved enough
            last = _last_saved_location.get(driver.id)
            if last:
                last_lat, last_lon, last_time = last
                dist = haversine_distance(lat, lon, last_lat, last_lon) * 1000
                time_diff = now - last_time
                if dist < MIN_MOVE_METERS and time_diff < MIN_SAVE_INTERVAL:
                    logger.debug(
                        f"⏭ Driver {driver.id} harakatlanmadi "
                        f"({dist:.1f}m), skip"
                    )
                    return

            # Save current location to cache
            _last_saved_location[driver.id] = (lat, lon, now)

            if is_web_active(driver.id):
                return
            await db.execute(
                text("""
                    UPDATE drivers
                    SET
                        current_latitude = :lat,
                        current_longitude = :lon,
                        location = ST_SetSRID(
                            ST_MakePoint(:lon, :lat), 4326
                        )::geography,
                        location_updated_at = NOW()
                    WHERE id = :driver_id
                """),
                {"driver_id": driver.id, "lat": lat, "lon": lon}
            )
            await db.commit()
            logger.debug(
                f"📍 Driver {driver.id} live location: "
                f"{lat:.6f}, {lon:.6f}"
            )

    except Exception as e:
        logger.error(f"Live location xato: {e}")


# ============================================
# BALANCE
# ============================================

@driver_router.message(F.text.in_(DRIVER_BALANCE_TEXTS))
async def show_balance(message: Message, lang: str = "uz"):
    """Balans va kunlik statistika"""
    try:
        async with AsyncSessionLocal() as db:
            lang = await db_lang_for_telegram(db, message.from_user.id)
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            if not user:
                return
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            if not driver:
                return

            # Tashkent "bugun" — UTC+5
            from datetime import datetime, timedelta
            now_utc = datetime.utcnow()
            now_tashkent = now_utc + timedelta(hours=5)
            today_tashkent_start = now_tashkent.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_utc_start = today_tashkent_start - timedelta(hours=5)

            # Bugungi yakunlangan safarlar
            from sqlalchemy import select, func
            from app.models.order import Order

            result = await db.execute(
                select(
                    func.count(Order.id).label("trips_today"),
                    func.coalesce(func.sum(Order.final_price), 0).label("earnings_today")
                ).where(
                    Order.driver_id == driver.id,
                    Order.status == "completed",
                    Order.completed_at >= today_utc_start
                )
            )
            row = result.one()
            trips_today = int(row.trips_today or 0)
            earnings_today = float(row.earnings_today or 0)

            total_earnings = float(driver.total_earnings or 0)
            balance = float(driver.balance or 0)

            text = (
                f"💰 <b>BALANS</b>\n\n"
                f"💵 Mavjud balans: <b>{balance:,.0f} so'm</b>\n"
                f"📊 Jami daromad: <b>{total_earnings:,.0f} so'm</b>\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📅 <b>Bugun</b>\n"
                f"🚕 Safarlar: <b>{trips_today} ta</b>\n"
                f"💵 Daromad: <b>{earnings_today:,.0f} so'm</b>"
            )

            await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"❌ Balans ko'rsatishda xato: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")


# ============================================
# PAYME CARD LINKING
# ============================================

@driver_router.message(F.text.in_(DRIVER_LINK_CARD_TEXTS))
async def link_card_start(message: Message, state: FSMContext, lang: str = "uz"):
    """Kartani bog'lash boshlash"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    await message.answer(
        get_text(lang, "driver_link_card_intro"),
        parse_mode="HTML"
    )
    await state.set_state(PaymeStates.waiting_for_card)


@driver_router.message(PaymeStates.waiting_for_card, F.text)
async def link_card_number(message: Message, state: FSMContext, lang: str = "uz"):
    """Karta raqami"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    card_number = message.text.replace(" ", "")
    
    if not card_number.isdigit() or len(card_number) != 16:
        await message.answer(get_text(lang, "driver_card_wrong_16"))
        return
    
    await state.update_data(card_number=card_number)
    
    await message.answer(
        get_text(lang, "driver_card_ok_expire")
    )
    await state.set_state(PaymeStates.waiting_for_expire)


@driver_router.message(PaymeStates.waiting_for_expire, F.text)
async def link_card_expire(message: Message, state: FSMContext, lang: str = "uz"):
    """Karta muddati va SMS yuborish"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    expire = message.text.replace("/", "").replace(" ", "")
    
    if not expire.isdigit() or len(expire) != 4:
        await message.answer(get_text(lang, "driver_card_wrong_mmyy"))
        return
    
    data = await state.get_data()
    card_number = data["card_number"]
    
    try:
        from app.services.payme_service import payme_service, PaymeError
        
        # Payme API'ga so'rov
        result = await payme_service.create_card(card_number, expire)
        
        # Result - dict bo'lishi kerak
        if not isinstance(result, dict):
            logger.error(f"❌ Payme noto'g'ri javob: {result}")
            await message.answer(
                get_text(lang, "driver_payme_error")
            )
            await state.clear()
            return
        
        temp_token = result.get("token")
        phone = result.get("phone", "")
        
        if not temp_token:
            logger.error(f"❌ Token yo'q: {result}")
            await message.answer(
                get_text(lang, "driver_payme_error")
            )
            await state.clear()
            return
        
        await state.update_data(
            temp_token=temp_token,
            phone=phone
        )
        
        await message.answer(
            get_text(lang, "driver_sms_prompt", phone=phone or "N/A"),
            parse_mode="HTML"
        )
        await state.set_state(PaymeStates.waiting_for_sms)
        
    except PaymeError as e:
        logger.error(f"Payme xato: {e.message} (code: {e.code})")
        await message.answer(
            get_text(lang, "driver_payme_error_reason", reason=e.message)
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Karta bog'lashda xato: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer(
            get_text(lang, "driver_generic_retry")
        )
        await state.clear()


@driver_router.message(PaymeStates.waiting_for_sms, F.text)
async def link_card_verify(message: Message, state: FSMContext, lang: str = "uz"):
    """SMS kodni tasdiqlash"""
    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, message.from_user.id)
    sms_code = message.text.strip()
    
    if not sms_code.isdigit() or len(sms_code) != 6:
        await message.answer(get_text(lang, "driver_sms_wrong_format"))
        return
    
    data = await state.get_data()
    temp_token = data["temp_token"]
    
    try:
        from app.services.payme_service import payme_service
        
        card_token = await payme_service.verify_card(temp_token, sms_code)
        
        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            if not user:
                await message.answer(get_text(lang, "driver_err_x"))
                await state.clear()
                return
            
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            if not driver:
                await message.answer(get_text(lang, "driver_err_x"))
                await state.clear()
                return
            
            driver.payme_token = card_token
            await db.commit()
        
        await state.clear()
        
        await message.answer(
            get_text(lang, "driver_card_linked_ok"),
            parse_mode="HTML"
        )
        
        logger.info(f"Driver {driver.id} kartani bog'ladi")
        
    except Exception as e:
        logger.error(f"SMS tasdiqlashda xato: {e}")
        await message.answer(
            get_text(lang, "driver_verify_error_detail", detail=str(e)[:100])
        )
        await state.clear()


# ============================================
# FINISH ORDER (SAFARNI YAKUNLASH)
# ============================================

@driver_router.callback_query(F.data.startswith("finish_order:"))
async def finish_order(callback: CallbackQuery):
    """Safarni yakunlash — yakuniy narx har doim serverda qayta hisoblanadi (WebApp bilan bir xil)."""
    try:
        order_id = int(callback.data.split(":")[1])
        async with AsyncSessionLocal() as db:
            from app.crud.order_crud import OrderCRUD
            from app.services.trip_billing import compute_server_final_price_for_completion
            from app.services.settings_service import SettingsLoadError

            order = await OrderCRUD.get_by_id(db, order_id)

            fin_lang = await db_lang_for_telegram(db, callback.from_user.id)
            if not order:
                await callback.answer(get_text(fin_lang, "driver_finish_order_closed"))
                return

            actor_user = await UserCRUD.get_by_telegram_id(db, callback.from_user.id)
            actor_driver = (
                await DriverCRUD.get_by_user_id(db, actor_user.id) if actor_user else None
            )
            if not actor_driver:
                logger.warning(
                    "finish_order: no driver profile telegram_id=%s order_id=%s",
                    callback.from_user.id,
                    order_id,
                )
                await callback.answer(
                    get_text(fin_lang, "driver_finish_not_driver"),
                    show_alert=True,
                )
                return
            if order.driver_id != actor_driver.id:
                logger.warning(
                    "finish_order: driver mismatch order_id=%s order_driver=%s actor_driver=%s tg=%s",
                    order_id,
                    order.driver_id,
                    actor_driver.id,
                    callback.from_user.id,
                )
                await callback.answer(
                    get_text(fin_lang, "driver_finish_not_your_order"),
                    show_alert=True,
                )
                return

            if order.status == OrderStatus.COMPLETED:
                await callback.answer(get_text(fin_lang, "driver_finish_order_closed"))
                return

            if order.status != OrderStatus.IN_PROGRESS:
                await callback.answer(
                    get_text(fin_lang, "driver_finish_wrong_status"),
                    show_alert=True,
                )
                return

            r = get_redis()
            trip_st = get_trip_state(r, order_id) if r else None

            try:
                fp, tariff_snap, d_km = await compute_server_final_price_for_completion(
                    db, order_id, order, trip_st=trip_st
                )
            except SettingsLoadError as e:
                logger.error("finish_order SettingsLoadError: %s", e)
                await callback.answer(
                    get_text(fin_lang, "driver_finish_billing_failed"),
                    show_alert=True,
                )
                return
            except Exception as e:
                logger.exception("finish_order compute_server_final_price: %s", e)
                await callback.answer(
                    get_text(fin_lang, "driver_finish_billing_failed"),
                    show_alert=True,
                )
                return

            logger.info(
                "[SERVER RECOMPUTE] order_id=%s final_price=%s distance_km=%s",
                order_id,
                fp,
                d_km,
            )

            updated_order = await OrderCRUD.update_status(
                db,
                order_id,
                OrderStatus.COMPLETED,
                distance_km=d_km,
                final_price=fp,
                tariff_snapshot_json=tariff_snap,
            )
            if not updated_order:
                await callback.answer(
                    get_text(fin_lang, "driver_finish_billing_failed"),
                    show_alert=True,
                )
                return

            if r is not None:
                try:
                    delete_trip_state(r, order_id)
                except Exception as del_e:
                    logger.warning("delete_trip_state order=%s: %s", order_id, del_e)

            if updated_order.driver_id:
                driver = await DriverCRUD.get_by_id(db, updated_order.driver_id)
                if driver:
                    driver.is_available = True
                    await db.commit()

            order = updated_order

            # Komissiya / keshbek (o'z sessiyasida)
            from app.services.commission import deduct_commission_on_trip_complete
            bonus_info = await deduct_commission_on_trip_complete(order)
            used_bonus     = int(bonus_info.get("used_bonus", 0))
            earned_cashback = int(bonus_info.get("earned_cashback", 0))
            payable_amount  = int(bonus_info.get("payable_amount", 0))
            commission_val  = int(bonus_info.get("commission", 0))

            # 3. HAYDOVCHIGA XABAR — minimalist format
            def _fmt(n: int) -> str:
                return f"{n:,}".replace(",", " ")

            payable_str = _fmt(payable_amount)
            used_str = _fmt(used_bonus)
            earned_str = _fmt(earned_cashback)

            final_price_int = int(fp)
            if used_bonus > 0:
                net_cash = final_price_int - used_bonus
                balance_change = used_bonus - commission_val
                driver_msg = (
                    f"✅ <b>Safar yakunlandi!</b>\n"
                    f"💵 Naqd: <b>{_fmt(net_cash)} so'm</b>\n"
                    f"🎁 Bonus: <b>{_fmt(used_bonus)} so'm</b>\n"
                    f"📉 Kom: <b>-{_fmt(commission_val)} so'm</b>\n"
                    f"📈 Balans: <b>+{_fmt(balance_change)} so'm</b>"
                )
            else:
                driver_msg = (
                    f"✅ <b>Safar yakunlandi!</b>\n"
                    f"💵 To'lov: <b>{_fmt(final_price_int)} so'm</b>\n"
                    f"📉 Kom: <b>-{_fmt(commission_val)} so'm</b>"
                )

            await callback.message.edit_text(driver_msg, parse_mode="HTML")

            # 4. MIJOZGA: FSM holatini tozalash + chek + bosh menyu (explicit async - no order.user lazy load)
            if not order_skip_customer_notifications(order):
                try:
                    from aiogram.fsm.storage.base import StorageKey
                    from app.bot.telegram_bot import bot as telegram_bot, dp
                    from app.bot.messages import get_text
                    from app.bot.keyboards.main_menu import get_main_keyboard

                    order_user = await UserCRUD.get_by_id(db, order.user_id) if order.user_id else None
                    customer_telegram_id = getattr(order_user, "telegram_id", None) if order_user else None
                    if not customer_telegram_id:
                        raise ValueError("Mijoz telegram_id topilmadi")
                    # State reset: mijoz FSM holatini to'liq tozalab, bosh holatga qaytarish
                    try:
                        key = StorageKey(bot_id=telegram_bot.id, chat_id=customer_telegram_id, user_id=customer_telegram_id)
                        user_fsm = FSMContext(storage=dp.storage, key=key)
                        await user_fsm.clear()
                    except Exception as state_err:
                        logger.warning(f"Mijoz FSM tozalashda xato: {state_err}")

                    user_lang = normalize_bot_lang(getattr(order_user, "language_code", None) or "uz")

                    from app.bot.tracking_message_cleanup import clear_user_tracking_message

                    tracking_mid = getattr(order, "user_tracking_message_id", None)
                    await clear_user_tracking_message(
                        callback.bot, customer_telegram_id, tracking_mid
                    )

                    msg = (
                        get_text(user_lang, "arrived_at_dest")
                        + "\n\n"
                        + get_text(user_lang, "trip_finished_thanks")
                        + "\n\n"
                        + get_text(
                            user_lang,
                            "user_final_bill",
                            payable=payable_str,
                            used=used_str,
                            earned=earned_str,
                        )
                        + "\n\n"
                        + get_text(user_lang, "rate_driver")
                    )
                    await callback.bot.send_message(
                        chat_id=customer_telegram_id,
                        text=msg,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate:1:{order.id}"),
                             InlineKeyboardButton(text="⭐ 2", callback_data=f"rate:2:{order.id}"),
                             InlineKeyboardButton(text="⭐ 3", callback_data=f"rate:3:{order.id}"),
                             InlineKeyboardButton(text="⭐ 4", callback_data=f"rate:4:{order.id}"),
                             InlineKeyboardButton(text="⭐ 5", callback_data=f"rate:5:{order.id}")]
                        ]),
                        parse_mode="HTML"
                    )
                    # Bosh menyu tugmalarini yuborish (Taksi chaqirish, Buyurtmalarim va hokazo)
                    main_kb = get_main_keyboard(user_lang)
                    await callback.bot.send_message(
                        chat_id=customer_telegram_id,
                        text=get_text(user_lang, "order_cancel_success"),
                        reply_markup=main_kb
                    )
                except Exception as e:
                    logger.error(f"Mijozga yakuniy xabar yuborishda xato: {e}")

            await callback.answer(get_text(fin_lang, "trip_completed_check"))

            # To‘liq online klaviatura: ReplyKeyboardRemove + yangi markup (callback.message emas — bot + chat_id)
            try:
                from app.bot.telegram_bot import bot as telegram_bot
                from app.bot.driver_reply_keyboard_restore import (
                    force_restore_driver_online_reply_keyboard,
                )

                driver_chat_id = int(callback.from_user.id)
                await force_restore_driver_online_reply_keyboard(
                    telegram_bot,
                    driver_chat_id,
                    fin_lang,
                    context=f"finish_order_callback order_id={order_id}",
                )
            except Exception as _kb_err:
                logger.warning("finish_order: keyboard restore failed: %s", _kb_err)

    except Exception as e:
        logger.error(f"❌ Safarni yakunlashda xato: {e}")
        try:
            async with AsyncSessionLocal() as _db:
                _l = await db_lang_for_telegram(_db, callback.from_user.id)
            await callback.answer(get_text(_l, "driver_err_fatal_short"), show_alert=True)
        except Exception:
            await callback.answer(get_text("uz", "driver_err_fatal_short"), show_alert=True)
