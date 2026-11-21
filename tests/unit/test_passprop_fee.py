from app.services.passprop_service import FEE, challenge_public


def test_challenge_fee_is_one_hundred():
    assert FEE == 100


def test_challenge_public_defaults_unpaid():
    body = challenge_public({})
    assert body["fee"] == "100"
    assert body["fee_status"] == "unpaid"
    assert body["refund_on_breach"] is True


def test_challenge_public_keeps_refunded_status():
    body = challenge_public({"challenge_fee_status": "refunded"})
    assert body["fee_status"] == "refunded"
