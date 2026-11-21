from app.connectors.pocketoption import (
    PocketOptionConnector,
    format_ssid,
    parse_auth_frame,
    parse_balance_frame,
    parse_session_payload,
)


def test_auth_frame_splits_demo_and_keeps_the_wire_string():
    frame = '42["auth",{"session":"kp8c3a2bd1ets0mqjvrsvjrdgv","isDemo":1,"uid":128160124,"platform":2}]'
    parsed = parse_auth_frame(frame)
    assert parsed is not None
    assert parsed["is_demo"] is True
    assert parsed["uid"] == "128160124"
    assert parsed["wire"] == frame
    assert "session" not in str(parsed["uid"])


def test_real_auth_frame_is_not_demo():
    frame = '42["auth",{"session":"a:4:{s:10:\\"session_id\\";}","isDemo":0,"uid":42,"platform":2}]'
    parsed = parse_auth_frame(frame)
    assert parsed is not None
    assert parsed["is_demo"] is False


def test_balance_frame_reads_amount_without_returning_a_token():
    found = parse_balance_frame('42["balance_data",{"balance":1500.5,"currency":"USD"}]')
    assert found == {"balance": "1500.50", "currency": "USD"}
    assert parse_balance_frame("40") is None


def test_successauth_and_update_balance_frames_are_read():
    auth = parse_auth_frame('42["successauth",{"id":91974731,"isDemo":0,"balance":10.5}]')
    assert auth is not None
    assert auth["uid"] == "91974731"
    assert auth["is_demo"] is False
    found = parse_balance_frame('42["updateBalance",{"balance":88,"currency":"USD","isDemo":0}]')
    assert found == {"balance": "88.00", "currency": "USD", "is_demo": False}


def test_inspect_saves_a_captured_session_without_a_live_balance(monkeypatch):
    monkeypatch.setattr("app.connectors.pocketoption.read_session", lambda *args, **kwargs: None)
    result = PocketOptionConnector().inspect(
        {
            "uid": "91974731",
            "real_ssid": '42["auth",{"session":"kp8c3a2bd1ets0mqjvrsvjrdgv","isDemo":0,"uid":91974731}]',
            "real_balance": "",
            "real_currency": "USD",
        }
    )
    assert result["ok"] is True
    assert result["account"]["account_number"] == "91974731"
    assert result["account"]["equity"] == "0.00"


def test_inspect_uses_the_live_socket_balance(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.pocketoption.read_session",
        lambda *args, **kwargs: {"balance": "150.25", "currency": "USD", "uid": "91974731", "deals": []},
    )
    result = PocketOptionConnector().inspect(
        {
            "uid": "91974731",
            "real_ssid": '42["auth",{"session":"kp8c3a2bd1ets0mqjvrsvjrdgv","isDemo":0,"uid":91974731}]',
            "real_balance": "0.00",
            "real_currency": "USD",
        }
    )
    assert result["ok"] is True
    assert result["account"]["balance"] == "150.25"
    assert result["account"]["equity"] == "150.25"
    assert result["real"]["balance"] == "150.25"


def test_inspect_keeps_a_saved_balance_when_the_socket_is_quiet(monkeypatch):
    monkeypatch.setattr("app.connectors.pocketoption.read_session", lambda *args, **kwargs: None)
    result = PocketOptionConnector().inspect(
        {
            "uid": "91974731",
            "real_ssid": '42["auth",{"session":"kp8c3a2bd1ets0mqjvrsvjrdgv","isDemo":0,"uid":91974731}]',
            "real_balance": "88.50",
            "real_currency": "USD",
        }
    )
    assert result["account"]["equity"] == "88.50"


def test_binary_balance_blob_is_read():
    found = parse_session_payload({"balance": 1234.5, "currency": "USD", "uid": 91974731, "isDemo": 0})
    assert found is not None
    assert found["balance"] == "1234.50"
    assert found["uid"] == "91974731"
    assert found["is_demo"] is False
    nested = parse_session_payload([{"msg": {"balance": "10", "currency": "EUR"}}])
    assert nested is not None
    assert nested["balance"] == "10.00"
    assert nested["currency"] == "EUR"


def test_open_deals_map_to_trades(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.pocketoption.read_session",
        lambda *args, **kwargs: {
            "balance": "200.00",
            "currency": "USD",
            "uid": "91974731",
            "deals": [{"id": "deal-1", "asset": "EURUSD_otc", "amount": 5, "openPrice": 1.08, "closePrice": 1.0812, "command": 0, "profit": 0.4}],
        },
    )
    rows = PocketOptionConnector().fetch_positions(
        {"uid": "91974731", "real_ssid": '42["auth",{"session":"kp8c3a2bd1ets0mqjvrsvjrdgv","isDemo":0,"uid":91974731}]'}
    )
    assert len(rows) == 1
    assert rows[0].ticket == "deal-1"
    assert rows[0].symbol == "EURUSD_otc"
    assert rows[0].side == "buy"
    assert str(rows[0].volume) == "5"
    assert str(rows[0].entry_price) == "1.08"
    assert str(rows[0].current_price) == "1.0812"
    info = PocketOptionConnector().fetch_account(
        {"uid": "91974731", "real_ssid": '42["auth",{"session":"kp8c3a2bd1ets0mqjvrsvjrdgv","isDemo":0,"uid":91974731}]'}
    )
    assert str(info.balance) == "200.00"


def test_active_mode_reads_the_demo_book(monkeypatch):
    seen: list[bool] = []

    def fake_read(ssid, is_demo, uid="", url=""):
        seen.append(is_demo)
        return {"balance": "11.00" if is_demo else "99.00", "currency": "USD", "deals": []}

    monkeypatch.setattr("app.connectors.pocketoption.read_session", fake_read)
    creds = {
        "uid": "91974731",
        "active_mode": "demo",
        "demo_ssid": '42["auth",{"session":"demodemo12","isDemo":1,"uid":91974731}]',
        "real_ssid": '42["auth",{"session":"realreal12","isDemo":0,"uid":91974731}]',
    }
    info = PocketOptionConnector().fetch_account(creds)
    assert str(info.balance) == "11.00"
    assert seen[0] is True
    inspected = PocketOptionConnector().inspect(creds)
    assert inspected["account"]["server"] == "demo"
    assert inspected["account"]["balance"] == "11.00"


def test_complete_auth_wire_includes_fast_history():
    wire = '42["auth",{"session":"abc12345678","isDemo":0,"uid":1,"platform":1}]'
    built = format_ssid(wire, False, "1")
    assert built.startswith('42["auth",')
    assert '"isDemo":0' in built
    assert '"isFastHistory":true' in built
    assert '"session":"abc12345678"' in built
    rebuilt = format_ssid("n1p5ah5u8t9438rbunpgrq0hlq", True, "42")
    assert rebuilt.startswith('42["auth",')
    assert '"isDemo":1' in rebuilt
    assert '"isFastHistory":true' in rebuilt
    assert '"session":"n1p5ah5u8t9438rbunpgrq0hlq"' in rebuilt


def test_format_ssid_flips_demo_flag_on_a_real_wire():
    wire = '42["auth",{"session":"abc12345678","isDemo":0,"uid":1,"platform":2}]'
    flipped = format_ssid(wire, True, "1")
    assert '"isDemo":1' in flipped
    assert '"isFastHistory":true' in flipped
    assert '"session":"abc12345678"' in flipped
    assert '"platform":2' in flipped


def test_demo_switch_uses_the_real_session_on_demo_hosts(monkeypatch):
    seen: list[tuple[bool, str]] = []

    def fake_read(ssid, is_demo, uid="", url=""):
        seen.append((is_demo, url))
        assert "isDemo\":1" in format_ssid(ssid, is_demo, uid)
        return {"balance": "50.00", "currency": "USD", "deals": []}

    monkeypatch.setattr("app.connectors.pocketoption.read_session", fake_read)
    info = PocketOptionConnector().fetch_account(
        {
            "uid": "1",
            "active_mode": "demo",
            "real_ssid": '42["auth",{"session":"tokentoken12","isDemo":0,"uid":1}]',
            "ws_url": "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        }
    )
    assert str(info.balance) == "50.00"
    assert seen == [(True, "")]


def test_demo_live_is_ignored_when_the_socket_returns_the_real_book(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.pocketoption.read_session",
        lambda *args, **kwargs: {"balance": "0.80", "currency": "USD", "is_demo": False, "deals": []},
    )
    info = PocketOptionConnector().fetch_account(
        {
            "uid": "1",
            "active_mode": "demo",
            "demo_balance": "10000.00",
            "demo_currency": "USD",
            "real_ssid": '42["auth",{"session":"tokentoken12","isDemo":0,"uid":1}]',
        }
    )
    assert str(info.balance) == "10000.00"


def test_login_keeps_the_chosen_book_as_active_mode():
    from app.services.pocket_browser import PocketLogin

    session = PocketLogin("abc", "user-1", "demo")
    session.uid = "91974731"
    session.real_ssid = '42["auth",{"session":"tokentoken12","isDemo":0,"uid":91974731}]'
    creds = session.credentials()
    assert creds["active_mode"] == "demo"
    assert '"isDemo":1' in creds["demo_ssid"]
    snap = session._snapshot_body()
    assert snap["preferred_mode"] == "demo"
    assert snap["status"] == "waiting"
    assert snap["demo"] is not None
    assert snap["demo"]["balance"] == "—"
    assert "Real 0.80" not in snap["detail"]
    assert "Demo" in snap["detail"] or "demo" in snap["detail"].lower()


def test_demo_login_steers_to_the_demo_cabinet():
    from app.services.pocket_browser import PocketLogin

    session = PocketLogin("abc", "user-1", "demo")
    assert session._cabinet_url().endswith("/cabinet/demo-quick-high-low/")
    session.uid = "91974731"
    session.real_ssid = '42["auth",{"session":"tokentoken12","isDemo":0,"uid":91974731}]'
    assert session._should_steer() is True
    session.demo_ssid = '42["auth",{"session":"tokentoken12","isDemo":1,"uid":91974731}]'
    assert session._should_steer() is False


def test_untagged_real_balance_is_not_stored_as_demo():
    from app.services.pocket_browser import PocketLogin

    session = PocketLogin("abc", "user-1", "demo")
    session._note('{"balance":0.80,"uid":1,"currency":"USD"}')
    session._note('42["successauth",{"id":1,"isDemo":1}]')
    assert session.demo_balance == ""
    session._note('42["updateBalance",{"balance":10000,"currency":"USD","isDemo":1}]')
    assert session.demo_balance == "10000.00"


def test_successauth_balance_follows_the_auth_book():
    from app.services.pocket_browser import PocketLogin

    session = PocketLogin("abc", "user-1", "demo")
    session._note('42["successauth",{"id":1,"isDemo":1,"balance":50000,"currency":"USD"}]')
    assert session.demo_balance == "50000.00"
    assert session.real_balance == ""


def test_demo_snapshot_does_not_promote_a_real_balance(monkeypatch):
    from app.services.pocket_browser import PocketLogin

    monkeypatch.setattr(PocketLogin, "_kick_live", lambda self: None)
    session = PocketLogin("abc", "user-1", "demo")
    session.uid = "91974731"
    session.real_ssid = '42["auth",{"session":"tokentoken12","isDemo":0,"uid":91974731}]'
    session.real_balance = "0.80"
    snap = session.snapshot()
    assert snap["status"] == "waiting"
    assert snap["real"]["balance"] == "0.80"
    assert snap["demo"]["balance"] == "—"
    assert not snap["detail"].startswith("Real")


def test_pocket_active_mode_keeps_an_explicit_demo_choice():
    from app.services.account_service import _pocket_active_mode

    assert _pocket_active_mode({"active_mode": "demo", "real_ssid": "wire"}) == "demo"
    assert _pocket_active_mode({"real_ssid": "wire"}) == "real"
    assert _pocket_active_mode({"demo_ssid": "wire"}) == "demo"


def test_aucad_otc_maps_to_audcad_otc():
    from app.connectors.pocketoption import pocket_asset

    assert pocket_asset("aucad otc") == "AUDCAD_otc"
    assert pocket_asset("AUCAD OTC") == "AUDCAD_otc"
    assert pocket_asset("AUDCAD_otc") == "AUDCAD_otc"
    assert pocket_asset("EURUSD") == "EURUSD"


def test_binary_put_frame_is_a_one_minute_stake():
    from app.connectors.pocketoption import binary_order_frame

    frame = binary_order_frame("AUDCAD_otc", 100, "put", True, "req-1", 60)
    assert frame.startswith('42["openOrder",')
    assert '"asset":"AUDCAD_otc"' in frame
    assert '"action":"put"' in frame
    assert '"amount":100' in frame
    assert '"time":60' in frame
    assert '"isDemo":1' in frame
    assert '"optionType":100' in frame


def test_paused_pocket_refresh_does_not_write():
    from uuid import uuid4

    from app.services.live_trades import pause_pocket_refresh, refresh_terminal

    class Row:
        id = uuid4()
        connection_method = "pocketoption"
        status = "connected"
        display_name = "Pocket"

    pause_pocket_refresh(Row.id)
    assert refresh_terminal(None, Row) is None
