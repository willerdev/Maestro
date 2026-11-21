from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.expense_service import FEE
from app.services.license_service import (
    LicenseError,
    POOL_SIZE,
    activate_license,
    computer_name,
    device_fingerprint,
    mining_device_hash,
    new_code,
    normalize_code,
)


def test_operating_minimum_is_five_hundred():
    assert FEE == 500


def test_pool_has_ten_keys():
    assert POOL_SIZE == 10


def test_new_code_normalizes_to_itself():
    code = new_code()
    assert normalize_code(code) == code
    assert code.startswith("MAE-")
    assert len(code) == 18


def test_normalize_code_accepts_spaces_and_lowercase():
    assert normalize_code("mae abcd efgh ijkl") == "MAE-ABCD-EFGH-IJKL"
    assert normalize_code("MAEABCD EFGHIJKL") == "MAE-ABCD-EFGH-IJKL"
    assert normalize_code("short") == ""


def test_device_fingerprint_is_stable_and_rejects_short_ids():
    assert device_fingerprint("computer-one-device") == device_fingerprint("computer-one-device")
    assert device_fingerprint("computer-one-device") != device_fingerprint("computer-two-device")
    assert device_fingerprint("abc") == ""


def test_computer_name_identifies_browser_and_system():
    name = computer_name(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "abcdef123456",
    )
    assert name == "Chrome on macOS · abcdef"
    phone = computer_name(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "fedcba654321",
    )
    assert phone == "Safari on iPhone · fedcba"
    assert mining_device_hash("laptop-one-id") != mining_device_hash("laptop-two-id")
    assert mining_device_hash("") == mining_device_hash("anonymous-device-id")


def test_mining_computers_mark_this_machine_and_earnings():
    from app.services.chain_service import list_mining_computers

    org_id = uuid4()
    user_id = uuid4()
    current = device_fingerprint("desk-one-id")
    other = device_fingerprint("laptop-two-id")
    db = MagicMock()
    computer = SimpleNamespace(
        device_hash=current,
        label="Chrome on macOS · " + current[:6],
        last_seen=None,
    )
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [computer]),
        SimpleNamespace(all=lambda: []),
        SimpleNamespace(all=lambda: [other]),
    ]
    db.execute.side_effect = [
        SimpleNamespace(all=lambda: [(current, 250000000), (other, 100000000)]),
        SimpleNamespace(all=lambda: [(current, 50000000)]),
    ]
    rows = list_mining_computers(db, org_id, user_id, current)
    labels = {row["id"]: row for row in rows}
    assert labels[current[:12]]["this_computer"] is True
    assert labels[current[:12]]["earned"] == "3"
    assert labels[other[:12]]["this_computer"] is False
    assert labels[other[:12]]["pow_mined"] == "1"


def test_used_key_cannot_move_to_another_computer():
    user = SimpleNamespace(id=uuid4(), organization_id=uuid4())
    used = SimpleNamespace(
        status="used",
        device_hash=device_fingerprint("other-computer-id"),
        user_id=uuid4(),
        code="MAE-AAAA-BBBB-CCCC",
    )
    db = MagicMock()
    db.scalar.side_effect = [None, used]
    try:
        activate_license(db, user, ["TRADER"], "MAE-AAAA-BBBB-CCCC", "this-computer-id")
        raise AssertionError("expected error")
    except LicenseError as exc:
        assert exc.status == 409
        assert "another computer" in exc.detail
