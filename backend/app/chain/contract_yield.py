from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

MIN_BPS = 200
MAX_BPS = 298
DEFAULT_BPS = 200
MIN_DEPOSIT = Decimal("2000")
LOCK_DAYS = 7
_SCALE = Decimal("0.00000001")


def clamp_rate_bps(value: int) -> int:
    return max(MIN_BPS, min(MAX_BPS, int(value)))


def daily_yield(held: Decimal, rate_bps: int) -> Decimal:
    if held <= 0:
        return Decimal("0")
    points = clamp_rate_bps(rate_bps)
    return (held * Decimal(points) / Decimal(10_000)).quantize(_SCALE, rounding=ROUND_DOWN)


def working_day_profit(day, low: Decimal, high: Decimal) -> Decimal:
    if day.weekday() >= 5:
        return Decimal("0")
    low_cents = int((Decimal(low) * 100).to_integral_value(rounding=ROUND_DOWN))
    high_cents = int((Decimal(high) * 100).to_integral_value(rounding=ROUND_DOWN))
    if high_cents < low_cents:
        low_cents, high_cents = high_cents, low_cents
    span = high_cents - low_cents
    pick = low_cents if span == 0 else low_cents + (int(day.strftime("%Y%m%d")) % (span + 1))
    return (Decimal(pick) / Decimal(100)).quantize(_SCALE, rounding=ROUND_DOWN)


def rate_label(rate_bps: int) -> str:
    points = clamp_rate_bps(rate_bps)
    return f"{points / 100:.2f}%"


def unlock_at(started: datetime | None) -> datetime:
    stamp = started or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc) + timedelta(days=LOCK_DAYS)


def is_unlocked(started: datetime | None, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current >= unlock_at(started)
