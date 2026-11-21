from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.asset_service import AssetError, _available, approve_withdrawal, reject_withdrawal, request_withdrawal


def test_requested_withdrawal_holds_funds():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(direction="deposit", status="posted", amount=Decimal("10")),
        SimpleNamespace(direction="withdraw", status="requested", amount=Decimal("4")),
    ]
    assert _available(db, user, "usdttrc20") == Decimal("6")


def test_paused_withdrawal_holds_funds():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(direction="deposit", status="posted", amount=Decimal("10")),
        SimpleNamespace(direction="withdraw", status="paused", amount=Decimal("4")),
    ]
    assert _available(db, user, "usdttrc20") == Decimal("6")


def test_second_withdrawal_is_paused_while_one_is_open():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4(), email="user@example.com")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(direction="deposit", status="posted", amount=Decimal("20")),
        SimpleNamespace(direction="withdraw", status="pending", amount=Decimal("4"), user_id=user.id, organization_id=user.organization_id),
    ]
    db.scalar.return_value = SimpleNamespace(enabled=True, provider="nowpayments", organization_id=user.organization_id)
    with patch("app.services.asset_service.connector_for") as connector:
        with patch("app.services.asset_service.write_audit"):
            body = request_withdrawal(db, user, "usdttrc20", Decimal("5"), "TYh6P7x1k8mN3qR5sV7wY9zA2bC4dE6fG8", "127.0.0.1")
    assert body["status"] == "paused"
    connector.assert_not_called()
    assert db.add.call_args.args[0].status == "paused"


def test_finishing_a_withdrawal_resumes_the_oldest_paused_one():
    from datetime import datetime, timezone

    db = MagicMock()
    actor = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    owner = SimpleNamespace(id=uuid4(), email="user@example.com", full_name="Ada")
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 2, tzinfo=timezone.utc)
    paused_rows = [
        SimpleNamespace(id=uuid4(), direction="withdraw", status="paused", amount=Decimal("3"), created_at=newer, user_id=owner.id, organization_id=actor.organization_id),
        SimpleNamespace(id=uuid4(), direction="withdraw", status="paused", amount=Decimal("2"), created_at=older, user_id=owner.id, organization_id=actor.organization_id),
    ]
    row = SimpleNamespace(
        id=uuid4(),
        user_id=owner.id,
        organization_id=actor.organization_id,
        direction="withdraw",
        status="requested",
        currency="usdttrc20",
        amount=Decimal("5"),
        address="TYh6P7x1k8mN3qR5sV7wY9zA2bC4dE6fG8",
        invoice_url="",
        note="",
        provider_id="",
        created_at=None,
    )

    def getter(_model, ident):
        if ident == row.id:
            return row
        if ident == owner.id:
            return owner
        return None

    answers = [[], paused_rows]

    def scalars(_query):
        result = MagicMock()
        result.all.return_value = answers.pop(0) if answers else []
        return result

    db.get.side_effect = getter
    db.scalars.side_effect = scalars
    with patch("app.services.asset_service.write_audit"):
        reject_withdrawal(db, actor, ["ADMIN"], row.id, "not today", "127.0.0.1")
    assert paused_rows[1].status == "requested"
    assert paused_rows[0].status == "paused"


def test_rejected_withdrawal_releases_funds():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(direction="deposit", status="posted", amount=Decimal("10")),
        SimpleNamespace(direction="withdraw", status="rejected", amount=Decimal("4")),
    ]
    assert _available(db, user, "usdttrc20") == Decimal("10")


def test_user_request_does_not_send_payout():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4(), email="user@example.com")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [SimpleNamespace(direction="deposit", status="posted", amount=Decimal("20"))]
    config = SimpleNamespace(enabled=True, provider="nowpayments", organization_id=user.organization_id)
    db.scalar.return_value = config
    with patch("app.services.asset_service.connector_for") as connector:
        with patch("app.services.asset_service.write_audit"):
            body = request_withdrawal(db, user, "usdttrc20", Decimal("5"), "TYh6P7x1k8mN3qR5sV7wY9zA2bC4dE6fG8", "127.0.0.1")
    assert body["status"] == "requested"
    connector.assert_not_called()
    added = db.add.call_args.args[0]
    assert added.status == "requested"
    assert added.direction == "withdraw"


def test_approve_only_works_on_open_rows():
    db = MagicMock()
    actor = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    db.get.return_value = SimpleNamespace(direction="withdraw", status="posted", organization_id=actor.organization_id)
    try:
        approve_withdrawal(db, actor, ["SUPER_ADMIN"], uuid4(), "127.0.0.1")
        raise AssertionError("expected approve to fail")
    except AssetError as exc:
        assert exc.status == 400


def test_approve_posts_when_payout_fails():
    db = MagicMock()
    actor = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    owner = SimpleNamespace(id=uuid4(), email="user@example.com", full_name="Ada")
    row = SimpleNamespace(
        id=uuid4(),
        user_id=owner.id,
        organization_id=actor.organization_id,
        direction="withdraw",
        status="requested",
        currency="usdttrc20",
        amount=Decimal("5"),
        address="TYh6P7x1k8mN3qR5sV7wY9zA2bC4dE6fG8",
        invoice_url="",
        note="",
        provider_id="",
        order_id="",
        created_at=None,
    )

    def getter(_model, ident):
        if ident == row.id:
            return row
        if ident == owner.id:
            return owner
        return None

    db.get.side_effect = getter
    with patch("app.services.asset_service._nowpayments_org", side_effect=AssetError(400, "The default wallet is not ready")):
        with patch("app.services.asset_service.write_audit"):
            body = approve_withdrawal(db, actor, ["ADMIN"], row.id, "127.0.0.1")
    assert row.status == "posted"
    assert body["status"] == "posted"


def test_reject_marks_requested_row():
    db = MagicMock()
    actor = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    owner = SimpleNamespace(id=uuid4(), email="user@example.com", full_name="Ada")
    row = SimpleNamespace(
        id=uuid4(),
        user_id=owner.id,
        organization_id=actor.organization_id,
        direction="withdraw",
        status="requested",
        currency="usdttrc20",
        amount=Decimal("5"),
        address="TYh6P7x1k8mN3qR5sV7wY9zA2bC4dE6fG8",
        invoice_url="",
        note="",
        provider_id="",
        created_at=None,
    )
    def getter(_model, ident):
        if ident == row.id:
            return row
        if ident == owner.id:
            return owner
        return None

    db.get.side_effect = getter
    with patch("app.services.asset_service.write_audit"):
        body = reject_withdrawal(db, actor, ["ADMIN"], row.id, "not today", "127.0.0.1")
    assert row.status == "rejected"
    assert row.note == "not today"
    assert body["status"] == "rejected"
