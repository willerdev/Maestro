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
