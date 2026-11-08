from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.chain.contract_yield import clamp_rate_bps, daily_yield, is_unlocked, rate_label, unlock_at
from app.services.contract_service import _stake_view


def test_daily_yield_is_two_percent_on_two_thousand():
    earned = daily_yield(Decimal("2000"), 200)
    assert earned == Decimal("40")


def test_rate_stays_inside_two_to_two_point_ninety_eight():
    assert clamp_rate_bps(1) == 200
    assert clamp_rate_bps(400) == 298
    assert rate_label(250) == "2.50%"
    top = daily_yield(Decimal("2000"), 298)
    assert top == Decimal("59.6")


def test_funds_stay_locked_for_seven_days():
    started = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert unlock_at(started) == datetime(2026, 11, 8, tzinfo=timezone.utc)
    assert is_unlocked(started, datetime(2026, 11, 7, tzinfo=timezone.utc)) is False
    assert is_unlocked(started, datetime(2026, 11, 8, tzinfo=timezone.utc)) is True


def test_cancel_forfeits_yield_and_keeps_principal_locked():
    started = datetime.now(timezone.utc)
    view = _stake_view(
        SimpleNamespace(
            id=uuid4(),
            account_id=uuid4(),
            principal=Decimal("2000"),
            yield_earned=Decimal("80"),
            status="cancelled",
            created_at=started,
            last_yield_on=started.date(),
        ),
        "Contracts",
    )
    assert view["yield_earned"] == "0"
    assert view["held"] == "2000"
    assert view["can_cancel"] is False
    assert view["locked"] is True
    assert view["can_withdraw"] is False
