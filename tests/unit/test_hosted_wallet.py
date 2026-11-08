def test_deposit_credentials_need_only_the_api_key(monkeypatch):
    from app.core.config import get_settings
    from app.services.payment_service import _hosted_deposit_credentials

    settings = get_settings()
    monkeypatch.setattr(settings, "nowpayments_api_key", "live-api-key-123456")
    monkeypatch.setattr(settings, "nowpayments_ipn_secret", "")
    monkeypatch.setattr(settings, "nowpayments_payout_email", "")
    monkeypatch.setattr(settings, "nowpayments_payout_password", "")
    credentials = _hosted_deposit_credentials()
    assert credentials["api_key"] == "live-api-key-123456"


def test_stored_wallet_key_is_used_before_env(monkeypatch):
    from app.core.config import get_settings
    from app.services.payment_service import _hosted_deposit_credentials

    settings = get_settings()
    monkeypatch.setattr(settings, "nowpayments_api_key", "env-key")
    credentials = _hosted_deposit_credentials({"api_key": "admin-saved-key", "hosted": True})
    assert credentials["api_key"] == "admin-saved-key"


def test_usdt_ticker_becomes_trc20():
    from app.services.asset_service import _coin

    assert _coin("") == "usdttrc20"
    assert _coin("USDT") == "usdttrc20"
    assert _coin("USDT TRC20") == "usdttrc20"
    assert _coin("btc") == "btc"


def test_default_wallet_is_kept_without_calling_the_provider(monkeypatch):
    from app.core.config import get_settings
    from app.services.payment_service import _hosted_save_plan

    settings = get_settings()
    monkeypatch.setattr(settings, "nowpayments_api_key", "")
    monkeypatch.setattr(settings, "nowpayments_ipn_secret", "")
    monkeypatch.setattr(settings, "nowpayments_payout_email", "")
    monkeypatch.setattr(settings, "nowpayments_payout_password", "")
    credentials, probe_live = _hosted_save_plan()
    assert probe_live is False
    assert credentials["api_key"] == ""
    assert "secret" not in credentials["api_url"]
