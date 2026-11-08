from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from app.domain.rbac import allows
from app.services.admin_user_service import AdminUserError, allocate_wallet, set_user_banned, set_user_password
from app.services.asset_service import _coin


def test_only_admins_configure_connectors():
    assert allows(["ADMIN"], "system.configure")
    assert allows(["SUPER_ADMIN"], "system.configure")
    assert not allows(["TRADER"], "system.configure")
    assert not allows(["RISK_MANAGER"], "system.configure")


def test_admin_credit_uses_usdt_trc20():
    assert _coin("") == "usdttrc20"
    assert _coin("USDT") == "usdttrc20"


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
