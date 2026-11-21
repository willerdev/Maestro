from app.services.account_service import account_visibility
from app.services.system_config_service import merge_account_types


def test_traders_do_not_see_org_webhook_accounts():
    trader = account_visibility(["TRADER"])
    assert trader["org_wide"] is False
    assert trader["webhook"] is False
    risk = account_visibility(["RISK_MANAGER"])
    assert risk["org_wide"] is True
    assert risk["webhook"] is False
    owner = account_visibility(["SUPER_ADMIN"])
    assert owner["org_wide"] is True
    assert owner["webhook"] is True
    desk = account_visibility(["ADMIN"])
    assert desk["org_wide"] is True
    assert desk["webhook"] is True


def test_account_types_default_all_on():
    flags = merge_account_types(None)
    assert flags["metaapi"] is True
    assert flags["local_mt5"] is True
    assert flags["pocketoption"] is True
    assert flags["blockchain"] is True
    assert flags["mining"] is True
    assert flags["webhook"] is True
    assert flags["passprop"] is True


def test_account_types_can_turn_one_off():
    flags = merge_account_types({"mining": False, "pocketoption": 0})
    assert flags["mining"] is False
    assert flags["pocketoption"] is False
    assert flags["metaapi"] is True


def test_passprop_limit_is_ten():
    from app.services.account_service import _method_limit

    assert _method_limit("passprop") == 10
    assert _method_limit("pocketoption") == 5
    assert _method_limit("mining") == 20
    assert _method_limit("metaapi") == 1


def test_passprop_fields_need_a_firm_and_size():
    from app.services.account_service import AccountError, _passprop_fields

    try:
        _passprop_fields({"firm_name": "FT", "account_size": ""})
        raise AssertionError("expected size error")
    except AccountError as exc:
        assert "size" in exc.detail.lower()
    body = _passprop_fields({"firm_name": "FTMO", "firm_url": "https://ftmo.com", "rules": "5% daily", "account_size": "100,000"})
    assert body["firm_name"] == "FTMO"
    assert body["account_size"] == "100000"
    assert body["rules"] == "5% daily"


def test_unknown_account_type_is_ignored():
    flags = merge_account_types({"unknown": False, "metaapi": False})
    assert "unknown" not in flags
    assert flags["metaapi"] is False
