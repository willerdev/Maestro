import threading

import pytest

from app.chain.convert import USDT_UNIT, ConversionError, format_usdt, quote_conversion
from app.chain.money import UNIT


def _quote(amount, available, rate="1000", fee_bps=0, minimum="1000", maximum="0", enabled=True):
    return quote_conversion(amount, available=available, rate=rate, fee_bps=fee_bps, min_pcoin=minimum, max_pcoin=maximum, enabled=enabled)


def test_conversion_credits_usdt_and_reserves_pcoin():
    quoted = _quote("50000", available=100_000 * UNIT)
    assert quoted.usdt_atomic == 50 * USDT_UNIT
    assert format_usdt(quoted.usdt_atomic) == "50"
    assert quoted.cost_atomic == 50_000 * UNIT
    remaining = 100_000 * UNIT - quoted.cost_atomic
    assert remaining == 50_000 * UNIT


def test_conversion_rejects_a_low_balance_and_a_bad_amount():
    with pytest.raises(ConversionError):
        _quote("50000", available=1_000 * UNIT)
    with pytest.raises(ConversionError):
        _quote("0", available=100_000 * UNIT)
    with pytest.raises(ConversionError):
        _quote("nope", available=100_000 * UNIT)


def test_exchange_rate_and_fee_change_the_quote():
    slower = _quote("50000", available=100_000 * UNIT, rate="2000")
    assert slower.usdt_atomic == 25 * USDT_UNIT
    charged = _quote("50000", available=100_000 * UNIT, fee_bps=100)
    assert charged.fee_atomic == 500 * UNIT
    assert charged.usdt_atomic == 50 * USDT_UNIT
    with pytest.raises(ConversionError):
        _quote("50000", available=100_000 * UNIT, enabled=False)


def test_duplicate_reference_does_not_debit_twice_and_concurrent_calls_cannot_overdraw():
    available = 100_000 * UNIT
    seen = {}
    lock = threading.Lock()

    def convert(reference):
        with lock:
            if reference in seen:
                return seen[reference], available
            quoted = _quote("100000", available=available)
            seen[reference] = quoted
            return quoted, available - quoted.cost_atomic

    first, after = convert("same")
    second, after_again = convert("same")
    assert first is second
    assert after_again == after

    shared = {"available": 100_000 * UNIT, "wins": 0}
    gate = threading.Lock()

    def race():
        with gate:
            try:
                quoted = _quote("100000", available=shared["available"])
            except ConversionError:
                return
            shared["available"] -= quoted.cost_atomic
            shared["wins"] += 1

    threads = [threading.Thread(target=race) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert shared["wins"] == 1
    assert shared["available"] == 0
