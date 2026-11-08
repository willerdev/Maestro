from app.connectors import blockchain
from app.connectors.blockchain import BlockchainConnector, MiningConnector, balance_of_data, format_units


WALLET = "0x1111111111111111111111111111111111111111"
CONTRACT = "0x2222222222222222222222222222222222222222"
MINER = "0x3333333333333333333333333333333333333333"


def test_balance_call_pads_the_wallet():
    assert balance_of_data(WALLET) == "0x70a08231" + ("0" * 24) + ("1" * 40)


def test_units_drop_trailing_zeros():
    assert format_units(1_500_000_000_000_000_000, 18) == "1.5"


def test_private_key_is_rejected(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("a private key must not be sent to a chain")

    monkeypatch.setattr(blockchain, "read_native", explode)
    found = BlockchainConnector().inspect({"chain": "ethereum", "wallet_address": WALLET, "private_key": "0xabc"})
    assert found["ok"] is False
    assert found["error_code"] == "private_key_rejected"


def test_contract_reads_wallet_and_token(monkeypatch):
    monkeypatch.setattr(blockchain, "read_native", lambda chain, address: 2 * 10**18)
    monkeypatch.setattr(blockchain, "read_token", lambda chain, contract, wallet: (250 * 10**6, 6))
    found = BlockchainConnector().inspect({
        "chain": "ethereum",
        "wallet_address": WALLET,
        "contract_address": CONTRACT,
    })
    assert found["ok"] is True
    assert found["account"]["account_number"] == WALLET
    assert found["account"]["server"] == "contracts"
    assert found["account"]["equity"] == "2"
    assert "Contract 250" in found["detail"]
    assert "Mining" not in found["detail"]


def test_contract_requires_a_contract_address():
    found = BlockchainConnector().inspect({"chain": "ethereum", "wallet_address": WALLET})
    assert found["error_code"] == "contract_required"


def test_mining_reads_only_the_payout(monkeypatch):
    monkeypatch.setattr(blockchain, "read_native", lambda chain, address: 5 * 10**17)
    monkeypatch.setattr(blockchain, "read_token", lambda *args: (_ for _ in ()).throw(AssertionError("mining does not read a contract")))
    found = MiningConnector().inspect({"chain": "ethereum", "mining_address": MINER, "worker": "rig-1"})
    assert found["ok"] is True
    assert found["account"]["account_number"] == MINER
    assert found["account"]["server"] == "rig-1"
    assert "Mining 0.5 ETH" in found["detail"]
    assert "rig-1" in found["detail"]


def test_bitcoin_contract_is_rejected():
    found = BlockchainConnector().inspect({
        "chain": "bitcoin",
        "wallet_address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
        "contract_address": CONTRACT,
    })
    assert found["error_code"] == "contract_unsupported"
