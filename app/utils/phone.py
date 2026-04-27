import re


def normalize_phone(phone: str) -> str:
    s = (phone or "").strip()
    if not s:
        raise ValueError("phone is empty")

    if s.startswith("00"):
        s = "+" + s[2:]

    # keep only digits, preserve leading "+"
    if s.startswith("+"):
        s = "+" + re.sub(r"\D", "", s[1:])
    else:
        s = re.sub(r"\D", "", s)

    if s.startswith("998") and not s.startswith("+"):
        s = "+" + s

    if not re.fullmatch(r"\+998\d{9}", s):
        raise ValueError("invalid phone format")

    return s

