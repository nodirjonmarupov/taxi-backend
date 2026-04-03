"""
WebApp token - haydovchi taximeter uchun imzolangan token.
Faqat buyurtmani qabul qilgan haydovchi o'z buyurtmasini yangilashi mumkin.
"""
import hmac
import hashlib
import base64
import time
import logging
from typing import Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

TOKEN_TTL_SEC = 86400 * 7  # 7 kun (oldin 24 soat edi)


def generate_webapp_token(order_id: int, driver_id: int) -> str:
    """order_id va driver_id uchun imzolangan token yaratish."""
    ts = int(time.time())
    payload = f"{order_id}:{driver_id}:{ts}"
    secret = (settings.SECRET_KEY or "default-secret").encode()
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_webapp_token(token: str, order_id: int) -> Optional[Tuple[int, int]]:
    """
    Token tekshirish. (order_id, driver_id) qaytaradi yoki None.
    Muvaffaqiyatsizlik sababi log'ga yoziladi.
    """
    if not token:
        logger.warning("verify_webapp_token: token bo'sh")
        return None
    if not order_id:
        logger.warning("verify_webapp_token: order_id noto'g'ri (%s)", order_id)
        return None
    try:
        pad = 4 - len(token) % 4
        if pad != 4:
            token += "=" * pad
        raw = base64.urlsafe_b64decode(token).decode()
        parts = raw.split(":")
        if len(parts) != 4:
            logger.warning(
                "verify_webapp_token: token formati noto'g'ri — parts=%d (order_id=%s)",
                len(parts), order_id,
            )
            return None
        tok_oid, tok_did, ts_str, sig = parts
        tok_oid = int(tok_oid)
        tok_did = int(tok_did)
        ts = int(ts_str)
        if tok_oid != order_id:
            logger.warning(
                "verify_webapp_token: order_id mos emas — token=%d, request=%d",
                tok_oid, order_id,
            )
            return None
        age_sec = time.time() - ts
        if age_sec > TOKEN_TTL_SEC:
            logger.warning(
                "verify_webapp_token: token muddati o'tgan — yoshi=%.0fs, TTL=%ds (order=%d)",
                age_sec, TOKEN_TTL_SEC, order_id,
            )
            return None
        payload = f"{tok_oid}:{tok_did}:{ts}"
        secret = (settings.SECRET_KEY or "default-secret").encode()
        expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            logger.warning(
                "verify_webapp_token: HMAC imzo noto'g'ri — order=%d, driver=%d. "
                "SECRET_KEY farqli bo'lishi mumkin.",
                tok_oid, tok_did,
            )
            return None
        return (tok_oid, tok_did)
    except Exception as exc:
        logger.warning("verify_webapp_token: kutilmagan xato — %s", exc)
        return None
