import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import get_logger
from app.models.payment import PaymentTransaction
from app.models.user import Driver, User
from app.utils.phone import normalize_phone

logger = get_logger(__name__)

router = APIRouter(prefix="/payment", tags=["payment"])


class PaynetWebhookIn(BaseModel):
    phone: str
    amount: int
    transaction_id: str


@router.post("/webhook")
async def paynet_webhook(
    payload: PaynetWebhookIn,
    db: AsyncSession = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-KEY"),
):
    if not x_api_key or x_api_key != (settings.PAYNET_WEBHOOK_API_KEY or ""):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        phone_e164 = normalize_phone(payload.phone)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid phone")

    try:
        amount_uzs = int(payload.amount)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount")
    if amount_uzs <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    provider = "paynet"
    provider_tx_id = (payload.transaction_id or "").strip()
    if not provider_tx_id:
        raise HTTPException(status_code=400, detail="Invalid transaction_id")

    raw_payload = json.dumps(payload.model_dump(), ensure_ascii=False)

    driver: Optional[Driver] = None
    driver_user: Optional[User] = None

    async with db.begin():
        res = await db.execute(
            select(Driver, User)
            .join(User, User.id == Driver.user_id)
            .where(Driver.phone_e164 == phone_e164)
        )
        row = res.first()
        if row:
            driver, driver_user = row[0], row[1]

        tx = PaymentTransaction(
            provider=provider,
            provider_tx_id=provider_tx_id,
            driver_id=(driver.id if driver else None),
            phone_e164_snapshot=phone_e164,
            amount_uzs=amount_uzs,
            status=("accepted" if driver else "rejected"),
            raw_payload=raw_payload,
        )
        db.add(tx)
        try:
            await db.flush()
        except IntegrityError:
            # duplicate (provider, provider_tx_id) -> ignore
            return {"ok": True, "duplicate": True}

        if not driver:
            return {"ok": True, "status": "rejected", "reason": "driver_not_found"}

        driver.balance_uzs = int(driver.balance_uzs or 0) + amount_uzs

    # after commit: telegram notify
    try:
        if driver_user and getattr(driver_user, "telegram_id", None):
            from app.bot.telegram_bot import bot

            amt_txt = f"{amount_uzs:,}".replace(",", " ")
            bal_txt = f"{int(driver.balance_uzs):,}".replace(",", " ") if driver else "—"
            await bot.send_message(
                chat_id=driver_user.telegram_id,
                text=(
                    f"💰 +{amt_txt} so'm tushdi\n"
                    f"Balans: {bal_txt} so'm"
                ),
            )
    except Exception as e:
        logger.warning("Telegram notification failed: %s", e)

    logger.info(
        "PAYMENT SUCCESS | phone=%s amount=%s tx=%s",
        phone_e164,
        amount_uzs,
        provider_tx_id,
    )

    return {"ok": True}

