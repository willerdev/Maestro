"""Internal PCoin to USDT quotes. USDT here is an in-app balance, not a chain token."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from app.chain.money import UNIT, parse_amount

USDT_UNIT = 1_000_000


class ConversionError(Exception):
    pass


@dataclass(frozen=True)
class Quote:
    pcoin_atomic: int
    fee_atomic: int
    cost_atomic: int
    usdt_atomic: int
    rate: str


def format_usdt(units: int) -> str:
    sign = "-" if units < 0 else ""
    whole, frac = divmod(abs(int(units)), USDT_UNIT)
    text = f"{frac:06d}".rstrip("0")
    return f"{sign}{whole}" + (f".{text}" if text else "")


def parse_rate(text: str) -> Decimal:
    try:
        rate = Decimal(str(text).strip())
    except Exception as exc:
        raise ConversionError("Enter an exchange rate") from exc
    if rate <= 0:
        raise ConversionError("The exchange rate must be greater than zero")
    return rate


def quote_conversion(amount: str, *, available: int, rate: str, fee_bps: int, min_pcoin: str, max_pcoin: str, enabled: bool) -> Quote:
    if not enabled:
        raise ConversionError("Conversion is turned off")
    try:
        pcoin = parse_amount(amount)
    except ValueError as exc:
        raise ConversionError(str(exc)) from exc
    minimum = parse_amount(min_pcoin) if str(min_pcoin) not in {"", "0", "0.0"} else 0
    maximum = parse_amount(max_pcoin) if str(max_pcoin) not in {"", "0", "0.0"} else 0
    if minimum and pcoin < minimum:
        raise ConversionError("That amount is below the minimum conversion")
    if maximum and pcoin > maximum:
        raise ConversionError("That amount is above the maximum conversion")
    points = int(fee_bps)
    if points < 0 or points > 10_000:
        raise ConversionError("The conversion fee is invalid")
    fee = pcoin * points // 10_000
    cost = pcoin + fee
    if cost > available:
        raise ConversionError("The PCoin balance is too low")
    rate_value = parse_rate(rate)
    usdt = (Decimal(pcoin) / Decimal(UNIT) / rate_value * Decimal(USDT_UNIT)).to_integral_value(ROUND_DOWN)
    if usdt <= 0:
        raise ConversionError("That amount is too small to convert")
    return Quote(pcoin, fee, cost, int(usdt), format(rate_value, "f"))
