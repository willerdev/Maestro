from app.core.config import get_settings
from app.services.connection_probe import MetaApiTokenError, resolve_metaapi_credentials


def test_default_metaapi_token_replaces_anything_typed(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "metaapi_token", "server-token-value-1234567890")
    resolved = resolve_metaapi_credentials(
        {"token_source": "default", "token": "user-should-not-win", "metaapi_account_id": "abc12345"}
    )
    assert resolved["token"] == "server-token-value-1234567890"
    assert "token_source" not in resolved
    assert resolved["metaapi_account_id"] == "abc12345"
    assert "server-token-value-1234567890" != "user-should-not-win"


def test_broker_login_uses_the_saved_metaapi_token(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "metaapi_token", "server-token-value-1234567890")
    resolved = resolve_metaapi_credentials(
        {"token_source": "default", "broker": "IC Markets", "server": "ICMarketsSC-Demo", "login": "50194988", "password": "pw"}
    )
    assert resolved["token"] == "server-token-value-1234567890"
    assert resolved["login"] == "50194988"
    assert "token_source" not in resolved


def test_own_metaapi_token_is_left_unchanged():
    resolved = resolve_metaapi_credentials({"token": "own-token-value-1234567890", "metaapi_account_id": "abc12345"})
    assert resolved["token"] == "own-token-value-1234567890"


def test_missing_default_metaapi_token_is_rejected(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "metaapi_token", "")
    try:
        resolve_metaapi_credentials({"token_source": "default", "metaapi_account_id": "abc12345"})
    except MetaApiTokenError as exc:
        assert exc.detail == "The default MetaAPI token is not available"
    else:
        raise AssertionError("expected the default token to be unavailable")


def test_admin_saved_token_is_used_before_env(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "metaapi_token", "env-token-value-1234567890")
    resolved = resolve_metaapi_credentials(
        {"token_source": "default", "login": "50194988", "password": "pw"},
        fallback_token="admin-saved-token-1234567890",
    )
    assert resolved["token"] == "admin-saved-token-1234567890"
