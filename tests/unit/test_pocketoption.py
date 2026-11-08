from app.connectors.pocketoption import parse_auth_frame, parse_balance_frame


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
