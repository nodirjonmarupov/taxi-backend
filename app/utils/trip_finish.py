"""Safar yakunlash: taksometr (frontend) dan kelgan qiymatlarni tekshirish."""
from __future__ import annotations

from typing import Optional, Any

MAX_FINAL_PRICE = 99_999_999.0


def sanitize_distance_km(km: Any) -> float:
    """Masofa: manfiy yoki 1000 km dan oshsa 0 (noto'g'ri GPS)."""
    try:
        v = float(km or 0)
        if v < 0 or v > 1000:
            return 0.0
        return v
    except (TypeError, ValueError):
        return 0.0


def parse_client_final_price(value: Any) -> Optional[float]:
    """Taksometr yakuniy narxi: musbat, yuqori chegaradan oshmasin."""
    try:
        v = float(value)
        if v <= 0 or v > MAX_FINAL_PRICE:
            return None
        return round(v, 2)
    except (TypeError, ValueError):
        return None
