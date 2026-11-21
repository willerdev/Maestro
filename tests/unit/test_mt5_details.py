from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.account_service import AccountError, save_mt5_details


def test_mt5_details_need_login_password_and_server():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    with patch("app.services.system_config_service.method_is_open", return_value=True):
        with patch("app.services.expense_service.deposit_ready", return_value=True):
            try:
                save_mt5_details(MagicMock(), user, ["TRADER"], {"login": "100", "server": "Broker-Live"}, "127.0.0.1")
                raise AssertionError("expected missing password to fail")
            except AccountError as exc:
                assert exc.status == 400
                assert "password" in exc.detail.lower()
