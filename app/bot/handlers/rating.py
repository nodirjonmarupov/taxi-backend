from aiogram import Router, F, types
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.crud.order_crud import OrderCRUD
from app.core.logger import get_logger

logger = get_logger(__name__)
router = Router()

@router.callback_query(F.data.startswith("rate_"))
async def handle_rating(callback: CallbackQuery):
    """
    Mijoz ball berganda ishlaydigan handler.
    Format: rate_{order_id}_{ball}
    """
    try:
        # 1. Ma'lumotlarni ajratib olamiz
        data = callback.data.split("_")

        if len(data) < 3:
            await callback.answer("Ma'lumot noto'g'ri shakllangan", show_alert=True)
            return

        order_id = int(data[1])
        rating = int(data[2])

        # Validate rating range
        if not (1 <= rating <= 5):
            await callback.answer("Noto'g'ri reyting!", show_alert=True)
            return

        # Validate order_id
        if order_id <= 0:
            await callback.answer("Noto'g'ri buyurtma!", show_alert=True)
            return

        async with AsyncSessionLocal() as db:
            # 2. Buyurtmani olish va tekshirish
            order = await OrderCRUD.get_by_id(db, order_id)
            if not order:
                await callback.answer("Buyurtma topilmadi!", show_alert=True)
                return
            if not order.driver_id:
                await callback.answer("Buyurtmada haydovchi yo'q", show_alert=True)
                return

            # 3. Rating jadvalida saqlash va haydovchi reytingini yangilash
            from app.models.user import Rating
            from app.bot.handlers.user_handlers import update_driver_rating

            existing = await db.execute(
                select(Rating).where(Rating.order_id == order_id)
            )
            if existing.scalar_one_or_none():
                await callback.answer("Bu buyurtma allaqachon baholangan", show_alert=True)
                return

            new_rating = Rating(
                user_id=order.user_id,
                driver_id=order.driver_id,
                order_id=order.id,
                score=rating
            )
            db.add(new_rating)
            await db.commit()
            await update_driver_rating(db, order.driver_id)

            # 4. Buyurtma tugash vaqtini saqlash
            await OrderCRUD.update_rating(db, order_id, rating)

            # 6. Haydovchiga bildirishnoma yuborish (explicit async - no order.driver lazy load)
            from app.crud.user import DriverCRUD, UserCRUD
            driver_chat_id = None
            if order.driver_id:
                driver = await DriverCRUD.get_by_id(db, order.driver_id)
                if driver and driver.user_id:
                    driver_user = await UserCRUD.get_by_id(db, driver.user_id)
                    if driver_user:
                        driver_chat_id = getattr(driver_user, "telegram_id", None)
            if driver_chat_id:
                stars = "⭐" * rating
                
                driver_text = (
                    f"🌟 **Yangi reyting keldi!**\n\n"
                    f"Mijoz sizga {rating} ball berdi {stars}\n"
                    f"Buyurtma: `#{order_id}`\n\n"
                    f"Xizmatingiz uchun rahmat! 🚖"
                )
                
                try:
                    await callback.bot.send_message(
                        chat_id=driver_chat_id, 
                        text=driver_text,
                        parse_mode="Markdown"
                    )
                except Exception as send_error:
                    logger.error(f"Haydovchiga xabar yuborishda xatolik: {send_error}")

            # 7. Mijozga tasdiq xabari
            await callback.message.edit_text(
                f"Rahmat! Siz {rating} ball berdingiz. ✅\nFikringiz biz uchun muhim."
            )
            await callback.answer("Baho qabul qilindi!")

    except Exception as e:
        logger.error(f"Rating handlerda xatolik: {e}")
        await callback.answer("Tizimda xatolik yuz berdi.", show_alert=True)