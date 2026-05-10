"""
Order Service - Navbatma-navbat (Sequential) buyurtma tarqatish.
Har bir haydovchiga 15 soniya, keyingisi faqat timeout/rad dan keyin.
"""
import asyncio
from typing import Optional, Callable, Awaitable, List, Tuple, Any

from app.core.logger import get_logger

logger = get_logger(__name__)

DRIVER_TIMEOUT_SECONDS = 15
DRIVER_TIMER_INTERVAL = 4
DRIVER_CLOCK_EMOJIS = ['🕛', '🕒', '🕕', '🕘']

# order_id -> {event, task} — joriy taymer
_driver_timers: dict[int, dict] = {}

# order_id -> dispatch state
# candidates: [(driver_id, distance)], current_index, customer_telegram_id, customer_lang, is_driver
_dispatch_state: dict[int, dict] = {}


def _format_driver_timer_message(
    min_distance: float,
    first_name: str,
    remaining: int,
    customer_phone: str = "N/A",
) -> str:
    """Haydovchi xabari: soat emoji + progress bar"""
    elapsed = DRIVER_TIMEOUT_SECONDS - remaining
    clock = DRIVER_CLOCK_EMOJIS[(elapsed // DRIVER_TIMER_INTERVAL) % len(DRIVER_CLOCK_EMOJIS)]
    total_blocks = 10
    filled = int((elapsed / DRIVER_TIMEOUT_SECONDS) * total_blocks)
    filled = min(filled, total_blocks)
    empty = total_blocks - filled
    progress_bar = "▓" * filled + "░" * empty
    return (
        f"🚕 <b>YANGI BUYURTMA!</b>\n\n"
        f"📍 Masofa: {min_distance:.1f} km\n"
        f"👤 Mijoz: {first_name}\n\n"
        f"📞 Mijoz: {customer_phone or 'N/A'}\n\n"
        f"Sizga yangi buyurtma! Qabul qilish uchun vaqt: ({remaining}) soniya\n"
        f"{clock} [{progress_bar}]"
    )


def init_sequential_dispatch(
    order_id: int,
    candidates: List[Tuple[Any, float]],
    customer_telegram_id: int,
    customer_lang: str,
    is_driver: bool,
) -> None:
    """
    Navbatma-navbat tarqatishni boshlash.
    candidates: [(Driver, distance), ...] masofa bo'yicha saralangan.
    """
    # Serialize: (driver_id, distance)
    serialized = [(d.id, dist) for d, dist in candidates]
    _dispatch_state[order_id] = {
        "candidates": serialized,
        "current_index": 0,
        "customer_telegram_id": customer_telegram_id,
        "customer_lang": customer_lang,
        "is_driver": is_driver,
    }
    logger.info(f"Sequential dispatch init order {order_id}: {len(serialized)} drivers")


def clear_dispatch_state(order_id: int) -> None:
    """Tarqatish holatini tozalash (mijoz bekor qilganda)."""
    _dispatch_state.pop(order_id, None)


def stop_driver_timer(order_id: int) -> None:
    """Haydovchi qabul/rad qilganda taymerni to'xtatish"""
    data = _driver_timers.pop(order_id, None)
    if data:
        event = data.get("event")
        task = data.get("task")
        if event:
            event.set()
        logger.info(f"Driver timer stopped for order {order_id}")


async def _run_driver_accept_timer(
    bot,
    order_id: int,
    driver_chat_id: int,
    message_id: int,
    min_distance: float,
    first_name: str,
    customer_phone: str,
    on_timeout: Callable[[int], Awaitable[None]],
):
    """15 soniyalik qabul qilish taymeri."""
    key = order_id
    event = asyncio.Event()
    _driver_timers[key] = {"event": event, "task": None}

    try:
        for remaining in range(DRIVER_TIMEOUT_SECONDS - DRIVER_TIMER_INTERVAL, 0, -DRIVER_TIMER_INTERVAL):
            await asyncio.sleep(DRIVER_TIMER_INTERVAL)
            if event.is_set():
                return
            try:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                driver_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_order:{order_id}")],
                    [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_order:{order_id}")],
                ])
                await bot.edit_message_text(
                    chat_id=driver_chat_id,
                    message_id=message_id,
                    text=_format_driver_timer_message(
                        min_distance,
                        first_name,
                        remaining,
                        customer_phone=customer_phone or "N/A",
                    ),
                    reply_markup=driver_kb,
                )
            except Exception:
                pass

        await asyncio.sleep(DRIVER_TIMER_INTERVAL)
        if event.is_set():
            return

        try:
            from aiogram.types import InlineKeyboardMarkup
            await bot.edit_message_text(
                chat_id=driver_chat_id,
                message_id=message_id,
                text="⏰ Vaqt tugadi. Buyurtma boshqa haydovchiga yuborildi.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
            )
        except Exception:
            pass

        await on_timeout(order_id)
        logger.info(f"Driver timer timeout for order {order_id}")

    except asyncio.CancelledError:
        pass
    finally:
        _driver_timers.pop(key, None)


async def offer_to_next_driver(order_id: int, from_timeout_or_reject: bool = False) -> None:
    """
    Keyingi haydovchiga taklif yuborish.
    from_timeout_or_reject=True: avvalgi haydovchi timeout/rad, indeksni oshirish.
    """
    from app.bot.telegram_bot import bot
    from app.core.database import AsyncSessionLocal
    from app.crud.user import UserCRUD, DriverCRUD
    from app.crud.order_crud import OrderCRUD
    from app.models.order import OrderStatus
    from app.bot.messages import get_text
    from app.bot.keyboards.main_menu import get_main_keyboard
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    if from_timeout_or_reject:
        stop_driver_timer(order_id)

    state = _dispatch_state.get(order_id)
    if not state:
        logger.warning(f"No dispatch state for order {order_id}")
        return

    candidates = state["candidates"]
    idx = state["current_index"]

    if from_timeout_or_reject:
        state["current_index"] = idx + 1
        idx = state["current_index"]

    customer_telegram_id = state["customer_telegram_id"]
    customer_lang = state["customer_lang"]
    is_driver = state["is_driver"]

    # Order holatini tekshirish — boshqa qabul qilgan bo‘lishi mumkin
    async with AsyncSessionLocal() as db:
        order = await OrderCRUD.get_by_id(db, order_id)
        if not order or order.status != OrderStatus.PENDING or order.driver_id:
            _dispatch_state.pop(order_id, None)
            return

    # Mijozga xabar (keyingi haydovchiga o‘tganda)
    if from_timeout_or_reject:
        try:
            await bot.send_message(
                customer_telegram_id,
                get_text(customer_lang, "driver_no_response"),
            )
        except Exception as e:
            logger.warning(f"Customer notification xato: {e}")

    if idx >= len(candidates):
        # Ro‘yxat tugadi
        _dispatch_state.pop(order_id, None)
        try:
            async with AsyncSessionLocal() as db:
                order = await OrderCRUD.get_by_id(db, order_id)
                if order and order.status == OrderStatus.PENDING and not order.driver_id:
                    order.status = OrderStatus.CANCELLED
                    await db.commit()
            await bot.send_message(
                customer_telegram_id,
                get_text(customer_lang, "no_taxi"),
                reply_markup=get_main_keyboard(customer_lang),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"No taxi notification xato: {e}")
        return

    # Ushbu haydovchiga yuborish
    driver_id, min_distance = candidates[idx]

    async with AsyncSessionLocal() as db:
        customer_user = await UserCRUD.get_by_telegram_id(db, customer_telegram_id)
        customer_phone = getattr(customer_user, "phone", None) if customer_user else None

        driver = await DriverCRUD.get_by_id(db, driver_id)
        if not driver:
            asyncio.create_task(offer_to_next_driver(order_id, from_timeout_or_reject=True))
            return
        driver_user = await UserCRUD.get_by_id(db, driver.user_id)
        if not driver_user or not driver_user.telegram_id:
            asyncio.create_task(offer_to_next_driver(order_id, from_timeout_or_reject=True))
            return

        try:
            driver_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_order:{order_id}")],
                [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_order:{order_id}")],
            ])
            first_name = getattr(driver_user, "first_name", None) or "Mijoz"
            driver_msg = await bot.send_message(
                chat_id=driver_user.telegram_id,
                text=_format_driver_timer_message(
                    min_distance,
                    first_name,
                    DRIVER_TIMEOUT_SECONDS,
                    customer_phone=customer_phone or "N/A",
                ),
                reply_markup=driver_kb,
                parse_mode="HTML",
            )

            asyncio.create_task(
                _run_driver_accept_timer(
                    bot,
                    order_id,
                    driver_user.telegram_id,
                    driver_msg.message_id,
                    min_distance,
                    first_name,
                    customer_phone or "N/A",
                    lambda oid: offer_to_next_driver(oid, from_timeout_or_reject=True),
                )
            )
        except Exception as e:
            logger.error(f"Driver xabar xato: {e}")
            asyncio.create_task(offer_to_next_driver(order_id, from_timeout_or_reject=True))


async def start_sequential_dispatch(order_id: int) -> None:
    """
    Birinchi (eng yaqin) haydovchiga taklif yuborish va taymerni ishga tushirish.
    """
    await offer_to_next_driver(order_id, from_timeout_or_reject=False)


# Eski API uchun (accept_order ichida stop_driver_timer)
run_driver_accept_timer = _run_driver_accept_timer
