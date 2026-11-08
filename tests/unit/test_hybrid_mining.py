from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.chain.money import UNIT, format_amount
from app.services.mining_plan_service import extra_atomic, settle_mining_upgrade


def test_free_multiplier_credits_nothing():
    assert extra_atomic(Decimal("10"), Decimal("1"), 86400) == 0


def test_gold_day_adds_ten_pcoin():
    assert extra_atomic(Decimal("10"), Decimal("2"), 86400) == 10 * UNIT
    assert format_amount(extra_atomic(Decimal("10"), Decimal("2"), 86400)) == "10"


def test_starter_hour_is_truncated_not_rounded_up():
    atomic = extra_atomic(Decimal("10"), Decimal("1.25"), 3600)
    assert atomic == int(Decimal("2.5") / Decimal("24") * UNIT)
    assert atomic < extra_atomic(Decimal("10"), Decimal("1.25"), 3601)


def test_daily_cap_blocks_over_issue():
    assert extra_atomic(Decimal("10"), Decimal("3"), 86400, cap_remaining=0) == 0
    assert extra_atomic(Decimal("10"), Decimal("3"), 86400, cap_remaining=UNIT) == UNIT


def test_elapsed_time_is_required():
    assert extra_atomic(Decimal("10"), Decimal("3"), 0) == 0
    assert extra_atomic(Decimal("10"), Decimal("3"), -5) == 0


def test_duplicate_paid_webhook_does_not_activate_again():
    upgrade_id = uuid4()
    payment = SimpleNamespace(status="paid", upgrade_id=upgrade_id, reference="MU1", amount=Decimal("30"))
    db = MagicMock()
    db.scalar.return_value = payment
    settle_mining_upgrade(db, uuid4(), "MU1", "paid", {"price_amount": "30"})
    db.get.assert_not_called()
    db.add.assert_not_called()


def test_failed_payment_does_not_activate():
    payment = SimpleNamespace(status="pending", upgrade_id=None, reference="MU2", amount=Decimal("30"), note="")
    db = MagicMock()
    db.scalar.return_value = payment
    settle_mining_upgrade(db, uuid4(), "MU2", "failed", {})
    assert payment.status == "failed"
    db.get.assert_not_called()


def test_underpaid_invoice_is_rejected():
    payment = SimpleNamespace(
        status="pending",
        upgrade_id=None,
        reference="MU3",
        amount=Decimal("30"),
        note="",
        plan_id=uuid4(),
        user_id=uuid4(),
    )
    db = MagicMock()
    db.scalar.return_value = payment
    settle_mining_upgrade(db, uuid4(), "MU3", "paid", {"price_amount": "1"})
    assert payment.status == "failed"
    assert "below" in payment.note


def test_expired_upgrade_is_not_active():
    from app.services import mining_plan_service

    now = datetime.now(timezone.utc)
    row = SimpleNamespace(status="active", ends_at=now - timedelta(minutes=1), plan_id=uuid4())
    db = MagicMock()
    db.scalar.return_value = row
    assert mining_plan_service.active_upgrade(db, uuid4(), uuid4()) is None
    assert row.status == "expired"
