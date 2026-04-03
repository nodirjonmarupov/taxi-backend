"""
Telegram bot for taxi platform.
Handles user and driver interactions.
"""
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from app.core.config import settings
from app.core.database import AsyncSessionLocal
# Handlerlarni import qilish
from app.bot.handlers import user_handlers, driver_handlers, communication_handlers


class TaxiBot:
    """Main Telegram bot class"""
    
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all bot handlers"""
        # 1. Common handlers (Buyruqlar birinchi)
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_help, Command("help"))
        
        # 2. User handlers (Mijoz funksiyalari)
        user_handlers.register_user_handlers(self.dp)
        
        # 3. Driver handlers (Haydovchi funksiyalari)
        driver_handlers.register_driver_handlers(self.dp)

        # 4. Communication handlers (Muloqot ko'prigi - ENG OXIRIDA)
        # Bu router deyarli barcha matn va ovozli xabarlarni tutib oladi,
        # shuning uchun u yuqoridagilarga xalaqit bermasligi uchun pastda turishi shart.
        self.dp.include_router(communication_handlers.comm_router)
    
    async def cmd_start(self, message: types.Message):
        """Handle /start command"""
        telegram_id = message.from_user.id # str() ga o'girish shart emas, modelda qandayligiga qarab
        
        async with AsyncSessionLocal() as db:
            from app.crud.user import user_crud # To'g'ri path
            
            user = await user_crud.get_user_by_telegram_id(db, str(telegram_id))
            
            if user:
                if user.role.value == "driver":
                    await message.answer(
                        f"Xush kelibsiz, {user.first_name}! 🚗\n\n"
                        "Haydovchi menyusi:\n"
                        "/available - Ishni boshlash (ON)\n"
                        "/unavailable - Dam olish (OFF)\n"
                        "/location - Lokatsiyani yangilash\n"
                        "/stats - Daromadlarni ko'rish"
                    )
                else:
                    await message.answer(
                        f"Xush kelibsiz, {user.first_name}! 🚕\n\n"
                        "Mijoz menyusi:\n"
                        "/order - Taksi chaqirish\n"
                        "/history - Buyurtmalar tarixi"
                    )
            else:
                await message.answer(
                    "TaxiBot-ga xush kelibsiz! 🚕\n\n"
                    "Iltimos, ro'yxatdan o'ting:\n"
                    "/register_user - Mijoz sifatida\n"
                    "/register_driver - Haydovchi sifatida"
                )
    
    async def cmd_help(self, message: types.Message):
        """Handle /help command"""
        help_text = """
🚕 <b>TaxiBot yordam bo'limi</b>

<b>Mijozlar uchun:</b>
/order - Taksi chaqirish
/history - Tarixni ko'rish

<b>Haydovchilar uchun:</b>
/available - Band emasman
/unavailable - Bandman
/location - Lokatsiyani yuborish

<b>Muloqot:</b>
Safar davomida haydovchi yoki mijozga bot orqali ovozli xabar yoki matn yuborishingiz mumkin.
        """
        await message.answer(help_text, parse_mode="HTML")
    
    async def start(self):
        """Start the bot"""
        try:
            logger.info("Starting Telegram bot...")
            # Botni polling qilishni boshlaymiz
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            await self.bot.session.close()
    
    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping Telegram bot...")
        await self.dp.stop_polling()
        await self.bot.session.close()


# Global bot instance
bot_instance: TaxiBot = None


async def start_bot():
    """Start bot instance"""
    global bot_instance
    bot_instance = TaxiBot()
    await bot_instance.start()


async def stop_bot():
    """Stop bot instance"""
    global bot_instance
    if bot_instance:
        await bot_instance.stop()