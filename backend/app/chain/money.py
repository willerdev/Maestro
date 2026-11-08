"""Exact coin amounts in atomic units. One coin is 100,000,000 units."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

UNIT = 100_000_000


def format_amount(units: int) -> str:
    sign = "-" if units < 0 else ""
    whole, frac = divmod(abs(int(units)), UNIT)
    text = f"{frac:08d}".rstrip("0")
    return f"{sign}{whole}" + (f".{text}" if text else "")


def parse_amount(text: str) -> int:
    raw = str(text).strip()
    if not raw or raw.startswith("+"):
        raise ValueError("Enter an amount")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Enter an amount") from exc
    if value <= 0:
        raise ValueError("Amount must be greater than zero")
    quantum = Decimal(1) / Decimal(UNIT)
    if value != value.quantize(quantum):
        raise ValueError("Amount supports 8 decimal places")
    return int(value * UNIT)
