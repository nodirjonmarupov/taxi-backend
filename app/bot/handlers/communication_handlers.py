from aiogram import Router, F, types
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.bot.lang_utils import db_lang_for_telegram
from app.models.order import Order, OrderStatus
from app.models.user import Driver, User
from loguru import logger

comm_router = Router()


@comm_router.callback_query(F.data == "user_chat_tip")
async def user_chat_tip(callback: CallbackQuery):
    """Mijoz: haydovchiga yozish eslatmasi (alert)."""
    from app.bot.messages import get_text

    async with AsyncSessionLocal() as db:
        lang = await db_lang_for_telegram(db, callback.from_user.id)
    await callback.answer(get_text(lang, "user_chat_tip_alert"), show_alert=True)


@comm_router.message(F.content_type.in_({'text', 'voice', 'photo'}))
async def chat_proxy_handler(message: types.Message, state: FSMContext):
    # 1. Agarda xabarda 'Online' yoki 'Offline' so'zlari bo'lsa, bu handlerni to'xtatish
    # Bu haydovchi handleriga xabarni o'tkazib yuborishni ta'minlaydi
    if message.text:
        text = message.text
        if "Online" in text or "Offline" in text or "Balans" in text:
            return # Hech narsa qilmaymiz, keyingi handler (driver_handler) ishlasin

    # 2. State tekshiruvi (Agar foydalanuvchi biror narsa to'ldirayotgan bo'lsa)
    current_state = await state.get_state()
    if current_state is not None:
        return

    # 3. Komandalar uchun
    if message.text and message.text.startswith('/'):
        return

    async with AsyncSessionLocal() as db:
        sender_tg_id = str(message.from_user.id)
        
        try:
            # Faqat ACCEPTED yoki STARTED bo'lgan buyurtmalarni qidiramiz
            # Aynan shu foydalanuvchi ishtirok etgan buyurtmani topish
            query = (
                select(Order)
                .options(
                    selectinload(Order.user),
                    selectinload(Order.driver).selectinload(Driver.user)
                )
                .where(Order.status.in_([OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]))
            )
            
            result = await db.execute(query)
            active_orders = result.scalars().all()
            
            target_id = None
            prefix = ""

            for order in active_orders:
                cust_tg = str(order.user.telegram_id) if order.user else ""
                driv_tg = str(order.driver.user.telegram_id) if (order.driver and order.driver.user) else ""

                if sender_tg_id == cust_tg:
                    target_id = driv_tg
                    prefix = "👤 <b>Mijoz:</b> "
                    break
                elif sender_tg_id == driv_tg:
                    target_id = cust_tg
                    prefix = "🚖 <b>Haydovchi:</b> "
                    break

            # 4. Agar suhbatdosh topilsa, xabarni relay qilish
            if target_id:
                await send_relay(message, target_id, prefix)
                return # Xabar yuborildi, boshqa handlerga o'tish shart emas

        except Exception as e:
            logger.error(f"Chat relay xatosi: {e}")

async def send_relay(message: types.Message, target_id: str, prefix: str):
    """Xabarni formatlab yuborish"""
    try:
        if message.text:
            await message.bot.send_message(chat_id=target_id, text=f"{prefix}{message.text}", parse_mode="HTML")
        elif message.voice:
            await message.bot.send_voice(chat_id=target_id, voice=message.voice.file_id, caption=f"{prefix}(Ovozli xabar)", parse_mode="HTML")
        elif message.photo:
            await message.bot.send_photo(chat_id=target_id, photo=message.photo[-1].file_id, caption=f"{prefix}{message.caption or ''}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Relay xatosi: {e}")