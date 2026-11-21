from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from app.domain.rbac import allows
from app.services.admin_user_service import AdminUserError, allocate_wallet, set_user_banned, set_user_password, set_user_role
from app.services.asset_service import CREDIT_PURPOSES, credit_purpose, _coin


def test_only_admins_configure_connectors():
    assert allows(["ADMIN"], "system.configure")
    assert allows(["SUPER_ADMIN"], "system.configure")
    assert not allows(["TRADER"], "system.configure")
    assert not allows(["RISK_MANAGER"], "system.configure")


def test_admin_credit_uses_usdt_trc20():
    assert _coin("") == "usdttrc20"
    assert _coin("USDT") == "usdttrc20"


def test_credit_purpose_defaults_to_earnings():
    assert credit_purpose("") == ("earnings", "Earnings")
    assert credit_purpose("mining") == ("mining_rewards", "Mining rewards")
    assert credit_purpose("blockchain_rewards") == ("blockchain_rewards", "Blockchain rewards")
    assert "earnings" in CREDIT_PURPOSES
    try:
        credit_purpose("lottery")
        raise AssertionError("expected error")
    except Exception as exc:
        assert getattr(exc, "status", 0) == 400


def test_zero_allocation_is_rejected():
    db = MagicMock()
    actor = MagicMock()
    actor.id = uuid4()
    actor.organization_id = uuid4()
    target = MagicMock()
    target.id = uuid4()
    target.organization_id = actor.organization_id
    db.get.return_value = target
    try:
        allocate_wallet(db, actor, ["SUPER_ADMIN"], target.id, Decimal("0"), "usdttrc20", "127.0.0.1")
        raise AssertionError("expected error")
    except AdminUserError as exc:
        assert exc.status == 400


def test_cannot_ban_own_login():
    db = MagicMock()
    actor = MagicMock()
    actor.id = uuid4()
    actor.organization_id = uuid4()
    db.get.return_value = actor
    try:
        set_user_banned(db, actor, ["SUPER_ADMIN"], actor.id, True, "127.0.0.1")
        raise AssertionError("expected error")
    except AdminUserError as exc:
        assert exc.status == 400
        assert "own login" in exc.detail


def test_owner_role_cannot_be_assigned():
    try:
        set_user_role(MagicMock(), MagicMock(), ["SUPER_ADMIN"], uuid4(), "SUPER_ADMIN", "127.0.0.1")
        raise AssertionError("expected error")
    except AdminUserError as exc:
        assert exc.status == 403
        assert "cannot be assigned" in exc.detail


def test_unknown_role_is_rejected():
    try:
        set_user_role(MagicMock(), MagicMock(), ["SUPER_ADMIN"], uuid4(), "BOSS", "127.0.0.1")
        raise AssertionError("expected error")
    except AdminUserError as exc:
        assert exc.status == 400


def test_weak_password_is_rejected():
    db = MagicMock()
    actor = MagicMock()
    actor.id = uuid4()
    actor.organization_id = uuid4()
    target = MagicMock()
    target.id = uuid4()
    target.organization_id = actor.organization_id
    db.get.return_value = target
    try:
        set_user_password(db, actor, ["ADMIN"], target.id, "short", "127.0.0.1")
        raise AssertionError("expected error")
    except AdminUserError as exc:
        assert exc.status == 400
        assert "12" in exc.detail
