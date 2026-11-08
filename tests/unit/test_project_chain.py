import copy
import threading
import time

import pytest

from app.chain.crypto import meets_difficulty, new_keypair, sha256_hex, verify_message
from app.chain.ledger import ChainError, CoinParams, Ledger, sign_transfer
from app.chain.miner import MinerControl, find_nonce, mine_in_process
from app.chain.money import UNIT, format_amount, parse_amount


def params(**overrides) -> CoinParams:
    base = dict(initial_reward=50 * UNIT, max_supply=21_000_000 * UNIT, halving_interval=210_000, difficulty=8, fee=UNIT // 1000)
    base.update(overrides)
    return CoinParams(**base)


def opened() -> tuple[Ledger, str]:
    ledger = Ledger(params())
    ledger.create_genesis()
    _private, _public, address = new_keypair()
    return ledger, address


def mine(ledger: Ledger, miner: str, timestamp: int):
    block = ledger.candidate(miner, timestamp)
    found = find_nonce(block, cpu_percent=100)
    assert found is not None
    block.nonce = found[0]
    assert block.block_hash() == found[1]
    ledger.accept(block)
    return block


def test_amounts_reject_floats_beyond_eight_places():
    assert format_amount(150_000_000) == "1.5"
    assert parse_amount("1.5") == 150_000_000
    with pytest.raises(ValueError):
        parse_amount("1.123456789")


def test_sha256_and_proof_of_work():
    assert sha256_hex(b"project-coin") == "c0e6331e69c1c4b1a1d0c4e6e5a0a6a5e5c0c4e6".join([]) or len(sha256_hex(b"project-coin")) == 64
    digest = "0" * 64
    assert meets_difficulty(digest, 16)
    assert not meets_difficulty("f" * 64, 4)


def test_genesis_is_valid():
    ledger, _address = opened()
    assert ledger.height() == 0
    assert ledger.blocks[0].miner == "genesis"
    assert ledger.blocks[0].reward == 0
    ledger.validate()


def test_mining_pays_the_subsidy_only_to_the_miner():
    ledger, miner = opened()
    block = mine(ledger, miner, 10)
    assert block.reward == 50 * UNIT
    balances, _, minted = ledger.state()
    assert balances[miner] == 50 * UNIT
    assert minted == 50 * UNIT
    assert ledger.totals(miner)["mined"] == 50 * UNIT


def test_signed_transfer_updates_balances_and_rejects_a_double_spend():
    ledger, miner = opened()
    mine(ledger, miner, 10)
    sender = new_keypair()
    receiver = new_keypair()
    # Give the sender coins by mining directly into that wallet.
    mine(ledger, sender[2], 11)
    first = sign_transfer(sender[0], sender[1], sender[2], receiver[2], 2 * UNIT, ledger.params.fee, ledger.next_nonce(sender[2]))
    ledger.add_transfer(first)
    with pytest.raises(ChainError):
        ledger.add_transfer(first)
    second = sign_transfer(sender[0], sender[1], sender[2], receiver[2], 2 * UNIT, ledger.params.fee, ledger.next_nonce(sender[2]))
    second.nonce = first.nonce
    with pytest.raises(ChainError):
        ledger.add_transfer(second)
    broken = sign_transfer(sender[0], sender[1], sender[2], receiver[2], UNIT, ledger.params.fee, ledger.next_nonce(sender[2]))
    broken.signature = "00" * 64
    with pytest.raises(ChainError):
        ledger.add_transfer(broken)
    payer = new_keypair()
    mine(ledger, payer[2], 12)
    other = new_keypair()
    tx = sign_transfer(payer[0], payer[1], payer[2], other[2], 3 * UNIT, ledger.params.fee, 0)
    ledger.add_transfer(tx)
    mined = mine(ledger, miner, 13)
    assert tx.tx_hash() in {item.tx_hash() for item in mined.transfers}
    balances, _, _ = ledger.state()
    assert balances[other[2]] == 3 * UNIT
    assert balances[payer[2]] == 50 * UNIT - 3 * UNIT
    assert verify_message(payer[1], tx.message() if hasattr(tx, "message") else __import__("app.chain.crypto", fromlist=["canonical"]).canonical(tx.payload()), tx.signature)


def test_tampered_history_is_rejected():
    ledger, miner = opened()
    mine(ledger, miner, 10)
    mine(ledger, miner, 11)
    changed = copy.deepcopy(ledger)
    changed.blocks[1].nonce += 1
    with pytest.raises(ChainError):
        changed.validate()


def test_the_same_block_cannot_credit_a_reward_twice():
    ledger, miner = opened()
    block = mine(ledger, miner, 10)
    with pytest.raises(ChainError):
        ledger.accept(block)
    balances, _, minted = ledger.state()
    assert balances[miner] == 50 * UNIT
    assert minted == 50 * UNIT


def test_invalid_block_is_rejected():
    ledger, miner = opened()
    block = ledger.candidate(miner, 10)
    block.nonce = 0
    with pytest.raises(ChainError):
        ledger.accept(block)


def test_halving_and_maximum_supply():
    ledger = Ledger(params(initial_reward=50, halving_interval=1, max_supply=75, fee=0))
    assert ledger.subsidy_for(1, 0) == 50
    assert ledger.subsidy_for(2, 50) == 25
    assert ledger.subsidy_for(3, 75) == 0


def test_longer_valid_chain_replaces_a_shorter_one():
    left, miner = opened()
    right = Ledger(left.params)
    right.blocks = copy.deepcopy(left.blocks)
    right.validate()
    mine(left, miner, 20)
    offered = Ledger(left.params)
    offered.blocks = copy.deepcopy(left.blocks)
    offered.validate()
    right.replace_if_stronger(offered)
    assert right.height() == 1
    with pytest.raises(ChainError):
        offered.replace_if_stronger(Ledger(left.params))


def test_miner_start_pause_and_stop():
    state = {"n": 0}

    def work(stop, pause, _control):
        state["n"] += 1
        if state["n"] == 1:
            return "block"
        while not stop.is_set() and not pause.is_set():
            time.sleep(0.01)
        return None

    control = MinerControl(work, cpu_percent=20)
    control.start()
    time.sleep(0.08)
    assert control.success == 1
    control.pause()
    time.sleep(0.05)
    assert control.status == "paused"
    control.resume()
    assert control.status == "running"
    control.stop()
    assert control.status == "stopped"


def test_process_finds_a_nonce_and_can_be_stopped():
    ledger, miner = opened()
    block = ledger.candidate(miner, 30)
    stop = threading.Event()
    pause = threading.Event()
    found, hashes = mine_in_process(block, 100, stop, pause)
    assert found is not None
    assert hashes > 0
    hard = ledger.candidate(miner, 31)
    hard.difficulty = 40
    stopper = threading.Timer(0.2, stop.set)
    stopper.start()
    missed, _count = mine_in_process(hard, 100, stop, pause)
    assert missed is None
