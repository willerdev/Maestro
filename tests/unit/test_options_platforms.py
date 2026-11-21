from app.connectors.options_platforms import (
    is_pocket_live,
    normalize_platform,
    platform_from_broker,
    platform_label,
    platform_of,
    public_platforms,
)
from app.connectors.pocketoption import PocketOptionConnector


def test_five_options_platforms_are_listed():
    rows = public_platforms()
    codes = [row["code"] for row in rows]
    assert codes == ["pocketoption", "iqoption", "quotex", "deriv", "olymptrade"]
    assert platform_label("iqoption") == "IQ Option"
    assert platform_from_broker("Quotex") == "quotex"


def test_platform_aliases_and_rejection():
    assert normalize_platform("IQ Options") == "iqoption"
    try:
        normalize_platform("binomo")
        raise AssertionError("expected unknown platform")
    except ValueError as exc:
        assert "Choose" in str(exc)


def test_inspect_uses_the_chosen_platform_name():
    result = PocketOptionConnector().inspect(
        {
            "options_platform": "quotex",
            "uid": "qx-1",
            "session_ok": True,
            "real_ssid": "browser-session",
            "real_balance": "12.50",
            "real_currency": "USD",
        }
    )
    assert result["ok"] is True
    assert result["account"]["broker"] == "Quotex"
    assert result["account"]["display_name"] == "Quotex"
    assert is_pocket_live({"options_platform": "quotex", "real_ssid": "browser-session"}) is False
    assert is_pocket_live({"real_ssid": '42["auth",{"session":"x"}]'}) is True
    assert platform_of({"broker": "Deriv"}) == "deriv"
