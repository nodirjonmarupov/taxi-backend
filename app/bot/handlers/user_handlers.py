"""
User Handlers - To'liq tuzatilgan, ko'p tilli
"""
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton,
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from datetime import datetime

from app.core.database import AsyncSessionLocal
from app.crud.user import UserCRUD, DriverCRUD
from app.models.user import UserRole, Driver
from app.models.order import Order, OrderStatus
from app.schemas.user import UserCreate
from app.core.logger import get_logger
from app.utils.distance import haversine_distance
from app.core.config import settings
from app.bot.messages import get_text, normalize_bot_lang
from app.bot.keyboards.main_menu import get_main_keyboard

logger = get_logger(__name__)

MIN_BALANCE = getattr(settings, "MIN_BALANCE", 5000.0)

user_router = Router()

# Til tanlash tugmalari
LANG_BUTTONS = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🇺🇿 O'zbekcha (Lotin)", callback_data="lang:uz")],
    [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
    [InlineKeyboardButton(text="🇺🇿 Ўзбекча (Кирилл)", callback_data="lang:uz_cyrl")],
])


class UserStates(StatesGroup):
    """User buyurtma holatlari"""
    waiting_for_pickup = State()


async def send_main_menu(message: Message, *, lang: str, is_driver: bool, name: str) -> None:
    """Main menyu faqat /start handlerida ko'rsatiladi."""
    keyboard = get_main_keyboard(lang)
    await message.answer(
        get_text(lang, "main_menu_cta"),
        parse_mode="HTML",
    )
    if is_driver:
        await message.answer(
            get_text(lang, "welcome_driver", name=name),
            reply_markup=keyboard,
        )
    else:
        await message.answer(
            get_text(lang, "welcome_user", name=name),
            reply_markup=keyboard,
        )


@user_router.message(CommandStart())
async def start(message: Message, state: FSMContext, lang: str = "uz"):
    """Har /start: FSM tozalash, keyin doim til tanlash (tilni istalgan vaqtda o'zgartirish).

    Asosiy menyu faqat til tanlangandan keyin (lang_selected) ko'rsatiladi.
    """
    try:
        # Force reset: barcha eski holatlarni o'chirish
        try:
            await state.clear()
        except Exception:
            pass

        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)

            if not user:
                user_data = UserCreate(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    role=UserRole.USER
                )
                user = await UserCRUD.create(db, user_data)
                logger.info(f"✅ Yangi user: {user.telegram_id}")

            # Doim birinchi til tanlash (oldingi tanlov matn sifatida — default uz)
            hint_lang = normalize_bot_lang(getattr(user, "language_code", None) or "uz")
            # Til tanlash inline'ni ko'rsatishdan oldin eski reply keyboard'ni olib tashlaymiz
            # (Telegram reply keyboard persistant bo'lishi mumkin).
            try:
                rm = await message.answer(" ", reply_markup=ReplyKeyboardRemove())
                try:
                    await rm.delete()
                except Exception:
                    pass
            except Exception:
                pass
            await message.answer(
                get_text(hint_lang, "choose_language"),
                reply_markup=LANG_BUTTONS,
            )
    except Exception as e:
        logger.error(f"❌ Start xato: {e}")
        await message.answer(get_text("uz", "error"))


@user_router.callback_query(F.data.startswith("lang:"))
async def lang_selected(callback: CallbackQuery, state: FSMContext, lang: str = "uz"):
    """Til tanlanganda bazaga yoziladi va asosiy menyu chiqadi (/start tilni qayta tanlash uchun)."""
    try:
        code = callback.data.split(":")[1]  # uz, ru, uz_cyrl
        if code not in ("uz", "ru", "uz_cyrl"):
            code = "uz"

        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, callback.from_user.id)
            if not user:
                await callback.answer(get_text(code, "error"), show_alert=True)
                return
            await UserCRUD.update_language(db, user.id, code)
            driver = await DriverCRUD.get_by_user_id(db, user.id)
            is_driver = driver is not None
            name = (user.first_name or "").strip() or "User"

        try:
            await callback.message.delete()
        except Exception:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

        await send_main_menu(callback.message, lang=code, is_driver=is_driver, name=name)
        await callback.answer(get_text(code, "lang_saved_toast"))
    except Exception as e:
        logger.error(f"❌ Til tanlash xato: {e}")
        await callback.answer(get_text("uz", "error"), show_alert=True)


ORDER_TAXI_BUTTON_TEXTS = {
    "🚕 TAKSI CHAQRISH",
    "🚕 Taksi chaqirish",
    "🚕 ЗАКАЗАТЬ ТАКСИ",
    "🚕 Заказать такси",
    "🚕 ТАКСИ ЧАҚИРИШ",
    "🚕 Такси чақириш",
}


@user_router.message(F.text.in_(ORDER_TAXI_BUTTON_TEXTS))
async def order_taxi(message: Message, state: FSMContext, lang: str = "uz"):
    """Taksi buyurtma boshlash"""
    await message.answer(
        get_text(lang, "order_taxi"),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text(lang, "send_location"), request_location=True)]],
            resize_keyboard=True,
        ),
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_for_pickup)


# pickup_location va buyurtma mantiqi app/handlers/order_handlers.py da (tasdiqlash taymeri bilan)


@user_router.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order_user(callback: CallbackQuery, lang: str = "uz"):
    """Buyurtmani bekor qilish — muzlatilgan bonusni qaytarish bilan."""
    try:
        order_id = int(callback.data.split(":")[1])
        
        async with AsyncSessionLocal() as db:
            from app.crud.order_crud import OrderCRUD
            from sqlalchemy import select as sa_select
            from app.models.order import Order as OrderModel
            from app.models.user import User as UserModel

            # Lock order to prevent double-cancel
            order_row = await db.execute(
                sa_select(OrderModel).where(OrderModel.id == order_id).with_for_update()
            )
            order = order_row.scalar_one_or_none()
            
            if not order:
                await callback.answer(get_text(lang, "order_not_found"), show_alert=True)
                return

            if order.status != OrderStatus.PENDING:
                await callback.answer(get_text(lang, "order_cancel_fail"), show_alert=True)
                return

            order.status = OrderStatus.CANCELLED

            # ── Muzlatilgan bonusni qaytarish ──
            frozen = Decimal(str(getattr(order, "frozen_bonus", 0) or 0))
            if frozen > 0:
                user_row = await db.execute(
                    sa_select(UserModel).where(UserModel.id == order.user_id).with_for_update()
                )
                user_for_refund = user_row.scalar_one_or_none()
                if user_for_refund is not None:
                    user_for_refund.bonus_balance = float(
                        Decimal(str(user_for_refund.bonus_balance or 0)) + frozen
                    )
                    order.frozen_bonus = Decimal("0")
                    logger.info(
                        f"♻️ Order {order_id} bekor: frozen bonus {frozen} so'm qaytarildi"
                    )

            await db.commit()

            from app.services.order_service import stop_driver_timer, clear_dispatch_state
            stop_driver_timer(order_id)
            clear_dispatch_state(order_id)

            await callback.message.edit_text(
                get_text(lang, "order_cancelled"),
                parse_mode="HTML"
            )
            
            user_obj = await UserCRUD.get_by_id(db, order.user_id)
            u_lang = getattr(user_obj, "language_code", None) or lang
            await callback.message.answer(
                get_text(u_lang, "order_cancel_success"),
                reply_markup=get_main_keyboard(u_lang)
            )
            
            await callback.answer("Bekor qilindi")
            logger.info(f"Order {order_id} bekor qilindi")
            
    except Exception as e:
        logger.error(f"❌ Bekor qilish xato: {e}")
        await callback.answer("❌ Xato")


@user_router.callback_query(F.data.startswith("rate_driver:"))
async def rate_driver(callback: CallbackQuery, lang: str = "uz"):
    """Haydovchini baholash"""
    try:
        parts = callback.data.split(":")
        order_id = int(parts[1])
        rating_score = int(parts[2])
        
        async with AsyncSessionLocal() as db:
            from app.models.user import Rating
            
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            
            if not order or not order.driver_id:
                await callback.answer(get_text(lang, "error"), show_alert=True)
                return

            # Takroriy baholashni tekshirish
            existing = await db.execute(
                select(Rating).where(
                    Rating.user_id == order.user_id,
                    Rating.driver_id == order.driver_id,
                    Rating.order_id == order.id
                )
            )
            
            if existing.scalar_one_or_none():
                await callback.answer(get_text(lang, "already_rated"), show_alert=True)
                return
            
            # Reyting yaratish
            new_rating = Rating(
                user_id=order.user_id,
                driver_id=order.driver_id,
                order_id=order.id,
                score=rating_score
            )
            db.add(new_rating)
            await db.commit()
            
            # Driver reytingini yangilash
            await update_driver_rating(db, order.driver_id)
            
            await callback.message.edit_text(
                get_text(lang, "rated_thanks", score=rating_score),
                parse_mode="HTML"
            )
            
            # Keyboard qaytarish
            user = await UserCRUD.get_by_id(db, order.user_id)
            if user:
                driver = await DriverCRUD.get_by_user_id(db, user.id)
                is_driver = driver is not None
            else:
                is_driver = False
            
            user_obj = await UserCRUD.get_by_id(db, order.user_id)
            u_lang = getattr(user_obj, "language_code", None) or lang
            await callback.message.answer(
                get_text(u_lang, "order_cancel_success"),
                reply_markup=get_main_keyboard(u_lang)
            )

            await callback.answer("✅")
            logger.info(f"Order {order_id}: {rating_score}/5 ball")
            
    except Exception as e:
        logger.error(f"❌ Baholash xato: {e}")
        await callback.answer("❌ Xato")


async def update_driver_rating(db, driver_id: int):
    """Driver reytingini yangilash"""
    try:
        from sqlalchemy import func
        from app.models.user import Rating
        
        result = await db.execute(
            select(
                func.avg(Rating.score).label('avg_rating'),
                func.count(Rating.id).label('total_ratings')
            ).where(Rating.driver_id == driver_id)
        )
        
        row = result.first()
        avg_rating = float(row.avg_rating) if row.avg_rating else 5.0
        total_ratings = row.total_ratings
        
        driver = await DriverCRUD.get_by_id(db, driver_id)
        
        if not driver:
            return
        
        driver.rating = round(avg_rating, 2)
        driver.total_ratings = total_ratings
        
        if avg_rating < 3.0:
            driver.is_available = False
            driver.blocked_reason = f"Reyting past: {avg_rating}/5.0"
            await db.commit()
            logger.warning(f"🚨 Driver {driver_id} bloklandi! Reyting: {avg_rating}")
        elif avg_rating < 3.5:
            await db.commit()
            logger.warning(f"⚠️ Driver {driver_id} past reyting: {avg_rating}")
        else:
            await db.commit()
            logger.info(f"Driver {driver_id} reyting: {avg_rating}/5.0")
            
    except Exception as e:
        logger.error(f"❌ Reyting yangilash xato: {e}")


@user_router.message(F.text.in_({"ℹ️ Ma'lumot", "ℹ️ Информация", "ℹ️ Маълумот"}))
async def info(message: Message, lang: str = "uz"):
    """Ma'lumot"""
    try:
        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            
            if user:
                driver = await DriverCRUD.get_by_user_id(db, user.id)
                is_driver = driver is not None
            else:
                is_driver = False
    except:
        is_driver = False
    
    await message.answer(
        get_text(lang, "info_text"),
        reply_markup=get_main_keyboard(lang),
        parse_mode="HTML"
    )


def _cancel_kb() -> InlineKeyboardMarkup:
    """Faqat bitta 'Bekor qilish' tugmasi."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cashback_toggle:off")],
    ])


def _allowed_bonus(balance: float, cap: float) -> int:
    """
    Foydalanuvchi ishlatishi mumkin bo'lgan bonus miqdori.
    Formula: min( (balance // 1000) * 1000, cap )
    """
    from decimal import Decimal
    raw = Decimal(str(balance))
    rounded = (raw // Decimal("1000")) * Decimal("1000")
    return int(min(rounded, Decimal(str(cap))))


# All 3 language variants for the cashback button (generated from messages)
_CASHBACK_BTN_TEXTS = frozenset(
    get_text(ln, "btn_orders") for ln in ("uz", "ru", "uz_cyrl")
)

MIN_CASHBACK_BALANCE = 1000  # Minimal ishlatish chegarasi (so'm)


@user_router.message(F.text.in_(_CASHBACK_BTN_TEXTS))
async def cashback_menu(message: Message, lang: str = "uz"):
    """💰 Cashback tugmasi — bir bosishda yoqiladi (agar balans yetarli bo'lsa)."""
    try:
        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            if not user:
                await message.answer(get_text(lang, "error"), reply_markup=get_main_keyboard(lang))
                return

            u_lang = getattr(user, "language_code", None) or lang
            balance = float(getattr(user, "bonus_balance", 0) or 0)
            already_on = bool(getattr(user, "use_cashback_next_order", False))

            from app.services.settings_service import get_settings
            tariff = await get_settings(db)
            cap = float(tariff.max_bonus_cap)

            # ── Balans yetarli emas ──
            if balance < MIN_CASHBACK_BALANCE:
                await message.answer(
                    f"⚠️ Balansingizda <b>{int(balance):,} so'm</b>."
                    f"\nIshlatish uchun kamida <b>1 000 so'm</b> kerak.".replace(",", " "),
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard(u_lang),
                )
                return

            # ── Allaqachon yoqilgan ──
            if already_on:
                bonus = _allowed_bonus(balance, cap)
                await message.answer(
                    f"✅ <b>Cashback allaqachon yoqiq!</b>\n\n"
                    f"Keyingi safaringizdan <b>{bonus:,} so'm</b> chegirma qilinadi.".replace(",", " "),
                    parse_mode="HTML",
                    reply_markup=_cancel_kb(),
                )
                return

            # ── Bir bosishda yoqish ──
            user.use_cashback_next_order = True
            await db.commit()

            bonus = _allowed_bonus(balance, cap)
            await message.answer(
                f"✅ <b>Cashback yoqildi!</b>\n\n"
                f"Safaringizdan <b>{bonus:,} so'm</b> chegirma qilinadi.".replace(",", " "),
                parse_mode="HTML",
                reply_markup=_cancel_kb(),
            )

    except Exception as e:
        logger.error(f"❌ Cashback menu xato: {e}")
        await message.answer(get_text(lang, "error"), reply_markup=get_main_keyboard(lang))


@user_router.callback_query(F.data.startswith("cashback_toggle:"))
async def cashback_toggle(callback: CallbackQuery, lang: str = "uz"):
    """❌ Bekor qilish tugmasi — cashback'ni o'chiradi."""
    try:
        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, callback.from_user.id)
            if not user:
                await callback.answer(get_text(lang, "error"), show_alert=True)
                return

            u_lang = getattr(user, "language_code", None) or lang
            user.use_cashback_next_order = False
            await db.commit()

        await callback.message.edit_text(
            "❌ <b>Cashback bekor qilindi.</b>",
            parse_mode="HTML",
        )
        await callback.answer("Bekor qilindi")

    except Exception as e:
        logger.error(f"❌ Cashback toggle xato: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)


@user_router.callback_query(F.data.startswith("bonus_request:"))
async def bonus_request(callback: CallbackQuery, lang: str = "uz"):
    """Aktiv order (eski yo'l) orqali bonus ishlatish — hali ham ishlaydi."""
    try:
        order_id = int(callback.data.split(":")[1])

        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, callback.from_user.id)
            if not user:
                await callback.answer(get_text(lang, "error"), show_alert=True)
                return

            from app.crud.order_crud import OrderCRUD

            order = await OrderCRUD.get_by_id(db, order_id)
            if not order or order.user_id != user.id:
                await callback.answer(get_text(lang, "order_not_found"), show_alert=True)
                return

            if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
                await callback.answer(get_text(lang, "time_or_data_gone"), show_alert=True)
                return

            if bool(getattr(order, "is_bonus_requested", False)):
                await callback.answer(get_text(lang, "bonus_request_already"), show_alert=True)
                return

            order.is_bonus_requested = True
            await db.commit()

        await callback.answer(get_text(lang, "bonus_request_success"), show_alert=True)

    except Exception as e:
        logger.error(f"❌ Bonus request xato: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)