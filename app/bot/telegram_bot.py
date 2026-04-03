"""
Telegram Bot - Real-time matching bilan, O'zbekcha
"""
import os
import sys
import atexit
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

LOCK_FILE = os.path.join(os.path.expanduser("~"), ".timgo_bot.lock")


def _kill_pid(pid: int) -> bool:
    """Protsessni to'xtatish (Windows va Unix)."""
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        else:
            os.kill(pid, 9)
        return True
    except Exception:
        return False


def check_single_instance():
    """Bitta bot instansiyasini kafolatlaydi - PID lock fayl orqali."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            try:
                os.kill(old_pid, 0)
            except (OSError, ValueError):
                pass
            else:
                _kill_pid(old_pid)
        except (OSError, ValueError):
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_lock():
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass


def kill_existing_bots():
    """Boshqa ishlab turgan bot protsesslarini to'xtatadi."""
    if sys.platform == "win32":
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0 or not result.stdout or result.stdout.strip() == "null":
                return
            import json
            data = result.stdout.strip()
            try:
                procs = json.loads(data) if data.startswith("[") else [json.loads(data)]
            except json.JSONDecodeError:
                return
            if not isinstance(procs, list):
                procs = [procs]
            current = os.getpid()
            for p in procs:
                try:
                    pid = int(p.get("ProcessId", 0))
                    cmd = (p.get("CommandLine") or "").lower()
                    if pid != current and ("uvicorn" in cmd or "main:app" in cmd or "telegram_bot" in cmd):
                        _kill_pid(pid)
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass
        return
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "telegram_bot|uvicorn.*main"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return
        current = os.getpid()
        for pid in result.stdout.strip().split("\n"):
            if pid:
                try:
                    p = int(pid.strip())
                    if p != current:
                        _kill_pid(p)
                except ValueError:
                    pass
    except Exception:
        pass


atexit.register(remove_lock)

from app.core.config import settings
from app.core.logger import get_logger
from app.bot.handlers.communication_handlers import comm_router
from app.bot.handlers.rating import router as rating_router

logger = get_logger(__name__)

# Bot va Dispatcher yaratish - YANGILANGAN FORMAT
bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML) # To'g'ri usuli shu
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


def _delete_webhook_sync():
    """Webhook ni sync orqali o'chirish (conflict oldini olish)."""
    try:
        import httpx
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        httpx.get(url, timeout=10)
    except Exception:
        pass


def _debug_log(msg: str, data: dict = None):
    # #region agent log
    try:
        import json
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "debug-8ab418.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId": "8ab418", "location": "telegram_bot.py", "message": msg, "data": data or {}, "timestamp": __import__("time").time() * 1000}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion

async def start_bot(drop_pending_updates: bool = True):
    """Botni ishga tushirish. Conflict (ikkilamchi instansiya) xatosini bartaraf etadi."""
    # #region agent log
    _debug_log("start_bot ENTRY", {"pid": os.getpid(), "platform": sys.platform})
    # #endregion
    # #region agent log
    old_lock_pid = None
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_lock_pid = f.read().strip()
        except Exception:
            pass
    _debug_log("BEFORE check_single_instance", {"pid": os.getpid(), "old_lock_pid": old_lock_pid})
    # #endregion
    kill_existing_bots()
    check_single_instance()
    _delete_webhook_sync()
    from app.bot.handlers.user_handlers import user_router
    from app.bot.handlers.driver_handlers import driver_router
    from app.bot.handlers.admin_handlers import admin_router
    from app.handlers.order_handlers import order_router
    from app.bot.middlewares.i18n import I18nMiddleware

    dp.message.middleware(I18nMiddleware())
    dp.callback_query.middleware(I18nMiddleware())

    dp.include_router(admin_router)
    dp.include_router(order_router)  # Tasdiqlash taymeri (pickup_location + order_confirm)
    dp.include_router(user_router)
    dp.include_router(driver_router)
    dp.include_router(comm_router)
    dp.include_router(rating_router)

    logger.info("Telegram bot ishga tushmoqda...")

    # Eski webhook va navbatdagi yangilanishlarni tozalash
    try:
        await bot.delete_webhook(drop_pending_updates=drop_pending_updates)
        logger.info("Webhook o'chirildi, navbat tozalandi, polling rejimiga o'tildi.")
    except Exception as e:
        logger.warning(f"Webhook o'chirishda ogohlantirish: {e}")

    await asyncio.sleep(5)
    logger.info("Telegram long-poll sessiyasi bo'shatildi, polling boshlanmoqda...")

    # Conflict xatosi bo'lsa, qayta urinish bilan xavfsiz polling
    max_conflict_retries = 10
    conflict_delay = 5

    for attempt in range(max_conflict_retries):
        try:
            await dp.start_polling(bot, skip_updates=drop_pending_updates)
            break
        except TelegramConflictError as e:
            # #region agent log
            _debug_log("TelegramConflictError caught", {"attempt": attempt, "pid": os.getpid()})
            # #endregion
            if attempt < max_conflict_retries - 1:
                logger.warning(
                    f"Telegram conflict (boshqa instansiya ishlayapti). "
                    f"{conflict_delay} soniya kutib, qayta urinish ({attempt + 1}/{max_conflict_retries})..."
                )
                await asyncio.sleep(conflict_delay)
            else:
                logger.error(
                    "Telegram conflict: boshqa instansiya getUpdates qilmoqda. "
                    "Docker ishlayapti bo'lsa: docker compose stop app. Yoki boshqa terminaldagi uvicorn ni to'xtating."
                )
                raise
        except asyncio.CancelledError:
            logger.info("Telegram bot to'xtatildi.")
            raise
        except Exception as e:
            logger.error(f"Telegram bot xatosi: {e}")
            raise


async def stop_bot():
    """Botni to'xtatish"""
    logger.info("Telegram bot to'xtatilmoqda...")
    await bot.session.close()


async def send_message_to_user(user_telegram_id: int, text: str):
    """Foydalanuvchiga Telegram xabari yuborish"""
    import aiohttp

    bot_token = settings.TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(
            url,
            json={
                "chat_id": user_telegram_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10,
        )


if __name__ == "__main__":
    asyncio.run(start_bot())