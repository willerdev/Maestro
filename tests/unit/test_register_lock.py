from unittest.mock import MagicMock, patch

from app.services.auth_service import AuthError, create_member, public_register_allowed, register_user


def test_public_register_closes_once_an_admin_exists():
    db = MagicMock()
    db.scalar.return_value = "admin-id"
    with patch("app.core.config.get_settings") as settings:
        settings.return_value = MagicMock(environment="development")
        assert public_register_allowed(db) is False


def test_public_register_stays_open_for_automated_tests():
    db = MagicMock()
    db.scalar.return_value = "admin-id"
    with patch("app.core.config.get_settings") as settings:
        settings.return_value = MagicMock(environment="test")
        assert public_register_allowed(db) is True


def test_register_user_refuses_a_second_admin():
    db = MagicMock()
    with patch("app.services.auth_service.ensure_rbac", lambda _db: None):
        with patch("app.services.auth_service.public_register_allowed", lambda _db: False):
            try:
                register_user(
                    db,
                    email="new@example.com",
                    password="Sup3rSecret12",
                    full_name="New",
                    organization_name="Other",
                    ip="127.0.0.1",
                )
                raise AssertionError("expected register to fail")
            except AuthError as exc:
                assert exc.status == 403
                assert "already has an owner" in exc.detail


def test_members_cannot_be_created_as_super_admin():
    db = MagicMock()
    actor = MagicMock()
    try:
        create_member(db, actor, email="a@b.com", password="Sup3rSecret12", full_name="A", role_code="SUPER_ADMIN", ip="127.0.0.1")
        raise AssertionError("expected create_member to fail")
    except AuthError as exc:
        assert exc.status == 403
        assert "cannot be created" in exc.detail.lower()
