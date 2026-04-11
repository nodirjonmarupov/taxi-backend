"""
Admin panel login brute-force protection: Redis when available, in-memory fallback.
After MAX_FAILED_ATTEMPTS failures, client IP is blocked for LOCKOUT_SECONDS.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.core.logger import get_logger
from app.core.redis import get_redis

logger = get_logger(__name__)

MAX_FAILED_ATTEMPTS = 5
FAIL_WINDOW_SECONDS = 600
LOCKOUT_SECONDS = 600

FAIL_KEY = "admin_login_fails:{ip}"
LOCK_KEY = "admin_login_lock:{ip}"

_memory_lock = threading.Lock()
_memory_fails: dict[str, tuple[int, float]] = {}
_memory_lock_until: dict[str, float] = {}


def client_ip_from_request(request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _redis_locked(ip: str) -> bool:
    r = get_redis()
    if r is None:
        return False
    try:
        return bool(r.exists(LOCK_KEY.format(ip=ip)))
    except Exception as e:
        logger.warning("admin_login lock check redis: %s", e)
        return False


def _redis_fail_and_maybe_lock(ip: str) -> None:
    r = get_redis()
    if r is None:
        return
    try:
        fk = FAIL_KEY.format(ip=ip)
        lk = LOCK_KEY.format(ip=ip)
        n = r.incr(fk)
        if n == 1:
            r.expire(fk, FAIL_WINDOW_SECONDS)
        if n >= MAX_FAILED_ATTEMPTS:
            r.setex(lk, LOCKOUT_SECONDS, "1")
            r.delete(fk)
    except Exception as e:
        logger.warning("admin_login fail redis: %s", e)


def _redis_clear(ip: str) -> None:
    r = get_redis()
    if r is None:
        return
    try:
        r.delete(FAIL_KEY.format(ip=ip), LOCK_KEY.format(ip=ip))
    except Exception as e:
        logger.warning("admin_login clear redis: %s", e)


def _memory_is_locked(ip: str) -> bool:
    with _memory_lock:
        until = _memory_lock_until.get(ip)
        if until is None:
            return False
        if time.time() >= until:
            del _memory_lock_until[ip]
            _memory_fails.pop(ip, None)
            return False
        return True


def _memory_fail_and_maybe_lock(ip: str) -> None:
    now = time.time()
    with _memory_lock:
        if ip in _memory_lock_until and now < _memory_lock_until[ip]:
            return
        if ip not in _memory_fails:
            _memory_fails[ip] = (1, now)
            return
        count, start = _memory_fails[ip]
        if now - start > FAIL_WINDOW_SECONDS:
            _memory_fails[ip] = (1, now)
            return
        count += 1
        _memory_fails[ip] = (count, start)
        if count >= MAX_FAILED_ATTEMPTS:
            _memory_lock_until[ip] = now + LOCKOUT_SECONDS
            _memory_fails.pop(ip, None)


def _memory_clear(ip: str) -> None:
    with _memory_lock:
        _memory_fails.pop(ip, None)
        _memory_lock_until.pop(ip, None)


def is_admin_login_locked(ip: str) -> bool:
    if get_redis() is not None:
        return _redis_locked(ip)
    return _memory_is_locked(ip)


def record_admin_login_failure(ip: str) -> None:
    if get_redis() is not None:
        _redis_fail_and_maybe_lock(ip)
    else:
        _memory_fail_and_maybe_lock(ip)


def clear_admin_login_failures(ip: str) -> None:
    _redis_clear(ip)
    _memory_clear(ip)


def lockout_message() -> str:
    return (
        "Too many failed login attempts. Try again in "
        f"{LOCKOUT_SECONDS // 60} minutes."
    )
