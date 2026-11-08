from app.chain.eth import address_from_private, parse_private_key


def test_known_private_key_one():
    address = address_from_private("0000000000000000000000000000000000000000000000000000000000000001")
    assert address.lower() == "0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"


def test_rejects_seed_phrase():
    try:
        parse_private_key("abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about")
    except ValueError as exc:
        assert "seed" in str(exc).lower() or "private key" in str(exc).lower()
    else:
        raise AssertionError("a seed phrase must be rejected")
