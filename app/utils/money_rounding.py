"""
Yagona 100 so'm qadam — Decimal ROUND_HALF_UP (bank yaxlitlash).
Barcha narx / keshbek / komissiya yaxlitlash shu funksiyadan o'tadi.
"""
from decimal import Decimal, ROUND_HALF_UP


def round_to_100_half_up(x: Decimal | float | int | str) -> int:
    """Butun so'm (100 qadam), HALF_UP."""
    d = x if isinstance(x, Decimal) else Decimal(str(x))
    unit = Decimal("100")
    q = (d / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit
    return int(q)
