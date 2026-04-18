"""
Order Handlers - Tasdiqlash taymeri bilan taksi buyurtma
10 soniyalik confirmation timer, asyncio.create_task, FSM OrderStates.confirm_order
"""
import asyncio
from decimal import Decimal, ROUND_DOWN
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.crud.user import UserCRUD, DriverCRUD
from app.crud.order_crud import OrderCRUD
from app.models.user import Driver, User, UserRole
from app.models.order import Order, OrderStatus
from app.core.logger import get_logger
from app.core.config import settings
from app.bot.handlers.user_handlers import UserStates
from app.bot.keyboards.main_menu import get_main_keyboard
from app.bot.messages import get_text
from app.services.matching import DriverMatchingService
from app.services.pricing_service import PricingService
from app.services.settings_service import get_settings

logger = get_logger(__name__)


class OrderStates(StatesGroup):
    """Buyurtma tasdiqlash bosqichi (FSM)"""
    confirm_order = State()

MIN_BALANCE = getattr(settings, "MIN_BALANCE", 5000.0)
CONFIRMATION_SECONDS = 10

order_router = Router()

# Har bir taymer uchun: (chat_id, message_id) -> asyncio.Event (user javob berganda set qilinadi)
_confirmation_events: dict[tuple[int, int], asyncio.Event] = {}
_confirmation_tasks: dict[tuple[int, int], asyncio.Task] = {}


CLOCK_EMOJIS = ['🕛', '🕐', '🕑', '🕒', '🕓', '🕔', '🕕', '🕖', '🕗', '🕘', '🕙', '🕚']


def _confirm_kb(lang: str = "uz"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_text(lang, "confirm_btn"), callback_data="order_confirm:yes"),
            InlineKeyboardButton(text=get_text(lang, "cancel_btn"), callback_data="order_confirm:no"),
        ]
    ])


def _format_timer_message(
    remaining: int,
    lang: str = "uz",
    prefix: str = "",
) -> str:
    """Vizual taymer: ixtiyoriy narx bloki + tasdiqlash + progress bar"""
    elapsed = CONFIRMATION_SECONDS - remaining
    clock = CLOCK_EMOJIS[elapsed % len(CLOCK_EMOJIS)]
    filled = elapsed
    empty = CONFIRMATION_SECONDS - filled
    progress_bar = "▓" * filled + "░" * empty
    title = get_text(lang, "confirm_order_title")
    remaining_txt = get_text(lang, "timer_remaining", remaining=remaining)
    body = f"{title}\n\n{remaining_txt}\n{clock} [{progress_bar}]"
    out = f"{prefix}{body}" if prefix else body
    # Telegram: bo'sh yoki faqat bo'sh joy — Bad Request: text must be non-empty
    if not (out or "").strip():
        out = get_text(lang, "confirm_order_title")
    return out


async def _run_confirmation_timer(
    bot,
    chat_id: int,
    message_id: int,
    state: FSMContext,
):
    """Har soniyada xabarni vizual tahrirlaydi (soat emoji + progress bar)."""
    key = (chat_id, message_id)
    event = asyncio.Event()
    _confirmation_events[key] = event

    try:
        data = await state.get_data()
        lang = data.get("lang", "uz")
        price_pre = data.get("pre_estimated_price")
        dist_pre = data.get("pre_distance_km")
        use_taximeter = data.get("use_taximeter_confirm", False)
        price_prefix = ""
        if use_taximeter:
            # Taksometr: oldindan narx ko'rsatilmaydi — faqat sarlavha + taymer
            price_prefix = ""
        elif price_pre is not None and dist_pre is not None:
            price_prefix = (
                get_text(lang, "confirm_order_price", price=price_pre, distance=dist_pre)
                + "\n\n"
            )
        for remaining in range(CONFIRMATION_SECONDS - 1, 0, -1):  # 9, 8, 7, ..., 1
            await asyncio.sleep(1)
            if event.is_set():
                return
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=_format_timer_message(remaining, lang, price_prefix),
                    reply_markup=_confirm_kb(lang),
                )
            except Exception:
                pass

        await asyncio.sleep(1)
        if event.is_set():
            return

        # Vaqt tugadi - asosiy menyuga qaytarish
        data = await state.get_data()
        is_driver = data.get("is_driver", False)
        lang = data.get("lang", "uz")
        await state.clear()

        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=get_text(lang, "time_expired"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
            )
        except Exception:
            pass

        await bot.send_message(
            chat_id=chat_id,
            text=get_text(lang, "order_cancelled_timeout"),
            reply_markup=get_main_keyboard(lang),
        )
        logger.info(f"Order confirmation timeout: chat_id={chat_id}")

    finally:
        _confirmation_events.pop(key, None)
        _confirmation_tasks.pop(key, None)


async def _create_and_distribute_order(
    message_or_callback,
    state: FSMContext,
    pickup_lat: float,
    pickup_lon: float,
    user_id: int,
    first_name: str,
    is_driver: bool,
    lang: str = "uz",
):
    """Buyurtmani bazaga saqlab, haydovchilarga tarqatish (taksometr: estimated_price DB uchun hisoblanadi)."""
    try:
        async with AsyncSessionLocal() as db:
            tariff = await get_settings(db)
            distance_km = 0.0
            estimated_price = PricingService.apply_tariff_and_round_to_100(distance_km, tariff)

            # ── Bonus freeze (SELECT FOR UPDATE ── race-condition himoyasi) ──
            # User row'ni lock qilamiz: bir vaqtda ikkita qurilmadan bosishda
            # faqat bitta tranzaksiya muvaffaqiyat bilan o'tadi.
            from app.models.user import User as UserModel
            user_locked = await db.execute(
                select(UserModel).where(UserModel.id == user_id).with_for_update()
            )
            user_obj = user_locked.scalar_one_or_none()

            # Bonusni safarga qo'llash: foydalanuvchi avvalgi "keyingi safar" tugmasisiz ham (default).
            wants_cashback = True
            frozen = Decimal("0")

            if wants_cashback and user_obj is not None:
                raw_balance = Decimal(str(getattr(user_obj, "bonus_balance", 0) or 0))

                # Qoida 1: 1 000 so'mga pastga yaxlitlash
                #   3 900 → 3 000 | 4 600 → 4 000 | 8 000 → 8 000
                rounded = (raw_balance // Decimal("1000")) * Decimal("1000")

                # Qoida 2: absolyut cap (settings.max_bonus_cap)
                cap = Decimal(str(tariff.max_bonus_cap))

                # Qoida 3: safar narxidan oshmasin (to'lov manfiy bo'lmasin)
                price_limit = Decimal(str(estimated_price or 0))

                # Formula: min(rounded_balance, cap, trip_price)
                # Foiz qoidasi YO'Q — faqat mutlaq limit.
                frozen = min(rounded, cap, price_limit)

                if frozen > 0:
                    # Balansdan ayirib, frozen_bonus'ga muzlatamiz
                    user_obj.bonus_balance = float(raw_balance - frozen)
                    if bool(getattr(user_obj, "use_cashback_next_order", False)):
                        user_obj.use_cashback_next_order = False

            new_order = Order(
                user_id=user_id,
                pickup_latitude=pickup_lat,
                pickup_longitude=pickup_lon,
                destination_latitude=pickup_lat,
                destination_longitude=pickup_lon,
                estimated_price=estimated_price,
                distance_km=distance_km,
                status=OrderStatus.PENDING,
                is_bonus_requested=(frozen > 0),
                frozen_bonus=frozen,
            )
            db.add(new_order)

            await db.commit()
            await db.refresh(new_order)
            logger.info(
                f"✅ Buyurtma yaratildi: {new_order.id} | "
                f"frozen_bonus={frozen} | cashback_requested={frozen > 0}"
            )

            cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text(lang, "cancel_btn"), callback_data=f"cancel_order:{new_order.id}")]
            ])

            send_fn = message_or_callback.message.answer if isinstance(message_or_callback, CallbackQuery) else message_or_callback.answer
            await send_fn(
                get_text(
                    lang,
                    "order_accepted_taximeter",
                    plat=pickup_lat,
                    plon=pickup_lon,
                ),
                reply_markup=cancel_kb,
            )

            # PostGIS orqali eng yaqin haydovchilarni topamiz (Python haversine matching'ni o‘chiramiz).
            candidates = await DriverMatchingService.find_nearest_drivers_postgis(
                db,
                pickup_lat,
                pickup_lon,
                radius_km=getattr(settings, "SEARCH_RADIUS_KM", 10.0),
                count=20,
                location_age_seconds=settings.LOCATION_FRESHNESS_SECONDS,
                exclude_user_id=user_id,
            )
            logger.info(
                f"🔍 Matching natija: {len(candidates)} ta haydovchi topildi "
                f"| radius={getattr(settings, 'SEARCH_RADIUS_KM', 10)}km "
                f"| MATCHING_TEST_MODE={getattr(settings, 'MATCHING_TEST_MODE', False)} "
                f"| pickup=({pickup_lat:.4f},{pickup_lon:.4f})"
            )

            # Adminlarni chiqarib tashlash — d.user (lazy) emas, batch User yuklash (async MissingGreenlet yo'q)
            if not getattr(settings, "ADMIN_CAN_RECEIVE_ORDERS", False):
                admin_telegram_ids = set(getattr(settings, "ADMIN_IDS", []))
                uids = list({d.user_id for d, _ in candidates if d.user_id})
                users_map: dict[int, User] = {}
                if uids:
                    ures = await db.execute(select(User).where(User.id.in_(uids)))
                    users_map = {u.id: u for u in ures.scalars().all()}
                filtered: list[tuple[Driver, float]] = []
                for d, dist in candidates:
                    u = users_map.get(d.user_id)
                    if not u:
                        continue
                    if u.role == UserRole.ADMIN:
                        continue
                    if u.telegram_id in admin_telegram_ids:
                        continue
                    filtered.append((d, dist))
                candidates = filtered

            if not candidates:
                logger.warning(
                    f"❌ Haydovchi topilmadi! order_id={new_order.id} "
                    f"radius={getattr(settings, 'SEARCH_RADIUS_KM', 10)}km "
                    f"age<={settings.LOCATION_FRESHNESS_SECONDS}s"
                )
                new_order.status = OrderStatus.CANCELLED
                # Muzlatilgan bonusni qaytarish
                if frozen > 0 and user_obj is not None:
                    user_obj.bonus_balance = float(
                        Decimal(str(user_obj.bonus_balance or 0)) + frozen
                    )
                    new_order.frozen_bonus = Decimal("0")
                await db.commit()
                await send_fn(
                    get_text(lang, "no_taxi"),
                    reply_markup=get_main_keyboard(lang),
                )
                return

            logger.info(f"🎯 Navbatma-navbat tarqatish: {len(candidates)} ta haydovchi, eng yaqin: {candidates[0][1]:.2f} km")

            cust = await UserCRUD.get_by_id(db, user_id)
            customer_telegram_id = getattr(cust, "telegram_id", None) if cust else None
            if not customer_telegram_id:
                new_order.status = OrderStatus.CANCELLED
                if frozen > 0 and user_obj is not None:
                    user_obj.bonus_balance = float(
                        Decimal(str(user_obj.bonus_balance or 0)) + frozen
                    )
                    new_order.frozen_bonus = Decimal("0")
                await db.commit()
                await send_fn(
                    get_text(lang, "no_taxi"),
                    reply_markup=get_main_keyboard(lang),
                )
                return

            try:
                from app.services.order_service import (
                    init_sequential_dispatch,
                    start_sequential_dispatch,
                )

                init_sequential_dispatch(
                    new_order.id,
                    candidates,
                    customer_telegram_id,
                    lang,
                    is_driver,
                )
                asyncio.create_task(start_sequential_dispatch(new_order.id))
            except Exception as e:
                logger.error(f"Sequential dispatch xato: {e}")
                new_order.status = OrderStatus.CANCELLED
                if frozen > 0 and user_obj is not None:
                    user_obj.bonus_balance = float(
                        Decimal(str(user_obj.bonus_balance or 0)) + frozen
                    )
                    new_order.frozen_bonus = Decimal("0")
                await db.commit()
                await send_fn(
                    get_text(lang, "no_taxi"),
                    reply_markup=get_main_keyboard(lang),
                )

    except Exception as e:
        logger.error(f"Buyurtma yaratish xato: {e}", exc_info=True)
        send_fn = message_or_callback.message.answer if isinstance(message_or_callback, CallbackQuery) else message_or_callback.answer
        await send_fn(
            get_text(lang, "error_try_again"),
            reply_markup=get_main_keyboard(lang),
        )


# --- Handlers ---


@order_router.message(UserStates.waiting_for_pickup, F.location)
async def pickup_location(message: Message, state: FSMContext, lang: str = "uz"):
    """Lokatsiya qabul qilish -> tasdiqlash xabari va taymer. Til: bazadagi language_code yoki middleware lang.

    Tasdiqlash bosqichi FSM: OrderStates.confirm_order (UserStates ichida alohida holat yo'q).
    """
    pickup_lat = message.location.latitude
    pickup_lon = message.location.longitude

    logger.info(f"👤 User {message.from_user.id} lokatsiya yubordi: {pickup_lat}, {pickup_lon}")

    try:
        async with AsyncSessionLocal() as db:
            user = await UserCRUD.get_by_telegram_id(db, message.from_user.id)
            if not user:
                await message.answer(get_text(lang, "error"), reply_markup=get_main_keyboard(lang))
                await state.clear()
                return

            # Foydalanuvchi tilini bazadan olish (bir marta tanlangan til butun jarayonda ishlatiladi)
            user_lang = getattr(user, "language_code", None) or lang
            driver_check = await DriverCRUD.get_by_user_id(db, user.id)
            is_driver = driver_check is not None

        await state.update_data(
            pickup_lat=pickup_lat,
            pickup_lon=pickup_lon,
            user_id=user.id,
            first_name=user.first_name or "Mijoz",
            is_driver=is_driver,
            lang=user_lang,
            use_taximeter_confirm=True,
        )
        # Tasdiqlash + inline tugmalar (Tasdiqlash / Bekor)
        await state.set_state(OrderStates.confirm_order)

        # Tasdiq oynasi: faqat "Taksi chaqirishni tasdiqlaysizmi?" + taymer (oldindan narx yo'q)
        text = _format_timer_message(CONFIRMATION_SECONDS, user_lang, "")

        # ReplyKeyboardRemove bilan yuboriladigan matn Telegramda bo'sh bo'lmasligi kerak (\u200b rad etiladi).
        dismiss_text = get_text(user_lang, "loc_received")
        if not (dismiss_text or "").strip():
            dismiss_text = "OK"
        logger.info(f"Yuborilayotgan matn (klaviatura yopish): {dismiss_text!r}")
        await message.answer(dismiss_text, reply_markup=ReplyKeyboardRemove())

        from app.bot.telegram_bot import bot
        logger.info(f"Yuborilayotgan matn (tasdiq taymeri): {text!r}")
        msg = await message.answer(
            text,
            reply_markup=_confirm_kb(user_lang),
        )

        key = (message.chat.id, msg.message_id)
        task = asyncio.create_task(
            _run_confirmation_timer(bot, message.chat.id, msg.message_id, state)
        )
        _confirmation_tasks[key] = task

    except Exception as e:
        logger.error(f"Pickup xato: {e}", exc_info=True)
        await state.clear()
        await message.answer(
            get_text(lang, "error_try_again"),
            reply_markup=get_main_keyboard(lang),
        )


@order_router.callback_query(StateFilter(OrderStates.confirm_order), F.data == "order_confirm:yes")
async def confirm_order_yes(callback: CallbackQuery, state: FSMContext, lang: str = "uz"):
    """Tasdiqlash -> taymerni to'xtat (Event + Task.cancel), broadcasting ishga tushsin"""
    key = (callback.message.chat.id, callback.message.message_id)
    event = _confirmation_events.get(key)
    if event:
        event.set()
    task = _confirmation_tasks.get(key)
    if task and not task.done():
        task.cancel()

    data = await state.get_data()
    if not data:
        await callback.answer(get_text(lang, "time_or_data_gone"), show_alert=True)
        try:
            await callback.message.edit_text(
                get_text(lang, "time_expired"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
            )
        except Exception:
            pass
        return

    pickup_lat = data.get("pickup_lat")
    pickup_lon = data.get("pickup_lon")
    user_id = data.get("user_id")
    first_name = data.get("first_name", "Mijoz")
    is_driver = data.get("is_driver", False)
    user_lang = data.get("lang", lang)
    pre_price = data.get("pre_estimated_price")
    pre_dist = data.get("pre_distance_km")

    if pickup_lat is None or pickup_lon is None or user_id is None:
        await callback.answer(get_text(user_lang, "data_error"), show_alert=True)
        await state.clear()
        return

    logger.info(
        f"confirm_order_yes: user_id={user_id} "
        f"pickup=({pickup_lat:.6f},{pickup_lon:.6f})"
    )

    try:
        await callback.message.edit_text(
            get_text(user_lang, "confirmed_short"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
        )
    except Exception:
        pass

    await state.clear()
    await callback.answer("OK")

    await _create_and_distribute_order(
        callback,
        state,
        float(pickup_lat),
        float(pickup_lon),
        user_id,
        first_name,
        is_driver,
        user_lang,
    )


@order_router.callback_query(StateFilter(OrderStates.confirm_order), F.data == "order_confirm:no")
async def confirm_order_no(callback: CallbackQuery, state: FSMContext, lang: str = "uz"):
    """Bekor qilish -> taymerni darhol to'xtat (Event + Task.cancel)"""
    key = (callback.message.chat.id, callback.message.message_id)
    event = _confirmation_events.get(key)
    if event:
        event.set()
    task = _confirmation_tasks.get(key)
    if task and not task.done():
        task.cancel()

    data = await state.get_data()
    is_driver = data.get("is_driver", False) if data else False
    user_lang = data.get("lang", lang) if data else lang
    await state.clear()

    try:
        await callback.message.edit_text(
            get_text(user_lang, "cancelled_short"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
        )
    except Exception:
        pass

    if not is_driver:
        try:
            async with AsyncSessionLocal() as db:
                user = await UserCRUD.get_by_telegram_id(db, callback.from_user.id)
                if user:
                    driver = await DriverCRUD.get_by_user_id(db, user.id)
                    is_driver = driver is not None
                    user_lang = getattr(user, "language_code", None) or user_lang
        except Exception:
            pass

    await callback.message.answer(
        get_text(user_lang, "order_cancel_success"),
        reply_markup=get_main_keyboard(user_lang),
    )
    await callback.answer("OK")
    logger.info(f"Order confirmation cancelled by user {callback.from_user.id}")
