import random
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.expense_service import FEE, MAX_CHARGE, MIN_CHARGE, hours_left, is_chargeable, next_expense_amount
from app.services.asset_service import _available


def test_hourly_plan_consumes_five_hundred():
    random.seed(11)
    remaining = FEE
    hours = 5 * 24
    taken = Decimal("0")
    while remaining > 0:
        cash = next_expense_amount(remaining, hours)
        assert cash > 0
        assert cash <= remaining
        if remaining > MAX_CHARGE:
            assert MIN_CHARGE <= cash <= MAX_CHARGE
        remaining -= cash
        taken += cash
        hours = max(1, hours - 1)
        if taken >= FEE:
            break
    assert taken == FEE
    assert remaining == 0


def test_charge_stays_inside_two_to_sixty_eight():
    random.seed(3)
    for hours in (120, 40, 8, 2):
        cash = next_expense_amount(FEE, hours)
        assert MIN_CHARGE <= cash <= MAX_CHARGE


def test_last_hour_takes_the_remainder():
    assert next_expense_amount(Decimal("41.25"), 1) == Decimal("41.25")


def test_super_admin_is_not_charged():
    assert is_chargeable(["SUPER_ADMIN"]) is False
    assert is_chargeable(["TRADER"]) is True
    assert is_chargeable(["ADMIN"]) is True


def test_posted_expense_reduces_available():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(direction="deposit", status="posted", amount=Decimal("500")),
        SimpleNamespace(direction="expense", status="posted", amount=Decimal("12.50")),
    ]
    assert _available(db, user, "usdttrc20") == Decimal("487.50")


def test_hours_left_never_drops_below_one():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 11, 8, tzinfo=timezone.utc)
    assert hours_left(now, now - timedelta(hours=2)) == 1
    assert hours_left(now, now + timedelta(hours=5, minutes=1)) == 6
