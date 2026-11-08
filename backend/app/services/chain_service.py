"""Store and serve one Project Coin chain per organization.

Confirmed balances come from replaying blocks. A request cannot set its own reward.
The running node is local. It does not claim to be a public network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chain.crypto import ADDRESS, address_for, new_keypair, public_from_private
from app.chain.ledger import Block, ChainError, CoinParams, Ledger, Reward, Transfer, sign_transfer
from app.chain.miner import MinerControl, mine_in_process
from app.chain.money import UNIT, format_amount, parse_amount
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.encryption import decrypt_json, encrypt_json
from app.models.chain_entities import ChainBlockRow, ChainHit, ChainNode, ChainSessionRow, ChainTxRow, ChainWallet

logger = logging.getLogger(__name__)

_ORG_LOCKS: dict[str, threading.Lock] = {}
_CONTROLS: dict[tuple[str, str], MinerControl] = {}
_CONTROL_LOCK = threading.Lock()


class ChainServiceError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def coin_params() -> CoinParams:
    settings = get_settings()
    return CoinParams(
        name=settings.chain_coin_name,
        symbol=settings.chain_symbol,
        max_supply=settings.chain_max_supply * UNIT,
        initial_reward=settings.chain_initial_reward * UNIT,
        halving_interval=settings.chain_halving_interval,
        difficulty=settings.chain_difficulty,
        fee=parse_amount(settings.chain_fee) if settings.chain_fee not in {"0", "0.0"} else 0,
    )


def _lock(org_id) -> threading.Lock:
    key = str(org_id)
    with _CONTROL_LOCK:
        if key not in _ORG_LOCKS:
            _ORG_LOCKS[key] = threading.Lock()
        return _ORG_LOCKS[key]


def _params_row(params: CoinParams) -> dict:
    return {
        "name": params.name,
        "symbol": params.symbol,
        "max_supply": format_amount(params.max_supply),
        "initial_reward": format_amount(params.initial_reward),
        "halving_interval": params.halving_interval,
        "difficulty": params.difficulty,
        "fee": format_amount(params.fee),
        "consensus": "proof-of-work",
        "hash": "sha256",
    }


def _transfer_from_dict(raw: dict) -> Transfer:
    return Transfer(
        sender=raw["sender"],
        recipient=raw["recipient"],
        amount=int(raw["amount"]),
        fee=int(raw["fee"]),
        nonce=int(raw["nonce"]),
        public_key=raw["public_key"],
        signature=raw["signature"],
    )


def _block_from_row(row: ChainBlockRow) -> Block:
    body = json.loads(row.body)
    reward = body.get("reward_tx")
    return Block(
        index=row.height,
        timestamp=int(row.timestamp),
        previous_hash=row.previous_hash,
        nonce=int(row.nonce),
        difficulty=row.difficulty,
        miner=row.miner_address,
        reward=int(row.reward),
        transfers=[_transfer_from_dict(item) for item in body.get("transfers", [])],
        reward_tx=Reward(reward["recipient"], int(reward["amount"]), int(reward["height"])) if reward else None,
    )


def _body(block: Block) -> str:
    reward = None
    if block.reward_tx is not None:
        reward = {"recipient": block.reward_tx.recipient, "amount": block.reward_tx.amount, "height": block.reward_tx.height}
    transfers = [
        {
            "sender": tx.sender,
            "recipient": tx.recipient,
            "amount": tx.amount,
            "fee": tx.fee,
            "nonce": tx.nonce,
            "public_key": tx.public_key,
            "signature": tx.signature,
        }
        for tx in block.transfers
    ]
    return json.dumps({"transfers": transfers, "reward_tx": reward})


def _remember(ledger: Ledger) -> None:
    ledger.confirmed = set()
    for block in ledger.blocks:
        for tx in block.transfers:
            ledger.confirmed.add(tx.tx_hash())
        if block.reward_tx is not None:
            ledger.confirmed.add(block.reward_tx.tx_hash())


def load_ledger(db: Session, org_id) -> Ledger:
    params = coin_params()
    rows = list(db.scalars(select(ChainBlockRow).where(ChainBlockRow.organization_id == org_id).order_by(ChainBlockRow.height)))
    ledger = Ledger(params)
    if not rows:
        with _lock(org_id):
            rows = list(db.scalars(select(ChainBlockRow).where(ChainBlockRow.organization_id == org_id).order_by(ChainBlockRow.height)))
            if rows:
                ledger.blocks = [_block_from_row(row) for row in rows]
            else:
                ledger.create_genesis()
                _insert_block(db, org_id, ledger.blocks[0])
                db.commit()
    else:
        ledger.blocks = [_block_from_row(row) for row in rows]
    if ledger.blocks and not ledger.confirmed:
        ledger.validate()
        _remember(ledger)
    pending = db.scalars(select(ChainTxRow).where(ChainTxRow.organization_id == org_id, ChainTxRow.block_height.is_(None), ChainTxRow.kind == "transfer").order_by(ChainTxRow.created_at))
    for row in pending:
        tx = Transfer(row.sender, row.recipient, int(row.amount), int(row.fee), int(row.nonce), row.public_key, row.signature)
        try:
            ledger.add_transfer(tx)
        except ChainError:
            db.delete(row)
    return ledger


def _insert_block(db: Session, org_id, block: Block) -> None:
    digest = block.block_hash()
    db.add(
        ChainBlockRow(
            organization_id=org_id,
            height=block.index,
            timestamp=block.timestamp,
            previous_hash=block.previous_hash,
            block_hash=digest,
            nonce=str(block.nonce),
            difficulty=block.difficulty,
            miner_address=block.miner,
            reward=block.reward,
            body=_body(block),
        )
    )
    for tx in block.transfers:
        existing = db.scalar(select(ChainTxRow).where(ChainTxRow.organization_id == org_id, ChainTxRow.tx_hash == tx.tx_hash()))
        if existing is None:
            db.add(_tx_row(org_id, tx.tx_hash(), "transfer", tx.sender, tx.recipient, tx.amount, tx.fee, tx.nonce, tx.public_key, tx.signature, block.index))
        else:
            existing.block_height = block.index
    if block.reward_tx is not None:
        reward = block.reward_tx
        db.add(_tx_row(org_id, reward.tx_hash(), "reward", "", reward.recipient, reward.amount, 0, 0, "", "", block.index))
    db.flush()


def _tx_row(org_id, tx_hash, kind, sender, recipient, amount, fee, nonce, public_key, signature, height) -> ChainTxRow:
    return ChainTxRow(
        organization_id=org_id,
        tx_hash=tx_hash,
        block_height=height,
        sender=sender,
        recipient=recipient,
        amount=amount,
        fee=fee,
        nonce=nonce,
        kind=kind,
        public_key=public_key,
        signature=signature,
    )


def _wallet(db: Session, org_id, user_id) -> ChainWallet | None:
    return db.scalar(select(ChainWallet).where(ChainWallet.organization_id == org_id, ChainWallet.user_id == user_id))


def _require_wallet(db: Session, org_id, user_id) -> ChainWallet:
    row = _wallet(db, org_id, user_id)
    if row is None:
        raise ChainServiceError(404, "Create a Project Coin wallet first")
    return row


def wallet_view(db: Session, org_id, user_id) -> dict:
    row = _require_wallet(db, org_id, user_id)
    ledger = load_ledger(db, org_id)
    balances, _, minted = ledger.state()
    totals = ledger.totals(row.address)
    params = ledger.params
    return {
        "address": row.address,
        "public_key": row.public_key,
        "available": format_amount(ledger.available(row.address)),
        "confirmed": format_amount(balances.get(row.address, 0)),
        "pending": format_amount(ledger.pending_incoming(row.address)),
        "mined": format_amount(totals["mined"]),
        "received": format_amount(totals["received"]),
        "sent": format_amount(totals["sent"]),
        "symbol": params.symbol,
        "coin": _params_row(params),
        "circulating": format_amount(minted),
    }


def create_wallet(db: Session, org_id, user_id) -> dict:
    if _wallet(db, org_id, user_id) is not None:
        raise ChainServiceError(409, "This account already has a Project Coin wallet")
    private, public, address = new_keypair()
    nonce, ciphertext = encrypt_json({"private_key": private})
    db.add(ChainWallet(organization_id=org_id, user_id=user_id, address=address, public_key=public, key_nonce=nonce, key_ciphertext=ciphertext))
    db.commit()
    logger.info("chain_wallet_created org=%s user=%s", org_id, user_id)
    return wallet_view(db, org_id, user_id)


def import_wallet(db: Session, org_id, user_id, private_key: str) -> dict:
    if _wallet(db, org_id, user_id) is not None:
        raise ChainServiceError(409, "This account already has a Project Coin wallet")
    raw = private_key.strip().lower()
    try:
        public = public_from_private(raw)
        address = address_for(public)
    except Exception as exc:
        raise ChainServiceError(400, "The private key is not a Project Coin key") from exc
    taken = db.scalar(select(ChainWallet).where(ChainWallet.address == address))
    if taken is not None:
        raise ChainServiceError(409, "That wallet already belongs to an account")
    nonce, ciphertext = encrypt_json({"private_key": raw})
    db.add(ChainWallet(organization_id=org_id, user_id=user_id, address=address, public_key=public, key_nonce=nonce, key_ciphertext=ciphertext))
    db.commit()
    logger.info("chain_wallet_imported org=%s user=%s", org_id, user_id)
    return wallet_view(db, org_id, user_id)


def export_wallet(db: Session, org_id, user_id) -> dict:
    row = _require_wallet(db, org_id, user_id)
    secret = decrypt_json(row.key_nonce, row.key_ciphertext)
    key = str(secret.get("private_key") or "")
    if not key:
        raise ChainServiceError(500, "The wallet key could not be read")
    return {"address": row.address, "private_key": key}


def send_coins(db: Session, org_id, user_id, recipient: str, amount: str) -> dict:
    row = _require_wallet(db, org_id, user_id)
    if not ADDRESS.match(recipient):
        raise ChainServiceError(400, "The recipient address is invalid")
    try:
        units = parse_amount(amount)
    except ValueError as exc:
        raise ChainServiceError(400, str(exc)) from exc
    with _lock(org_id):
        ledger = load_ledger(db, org_id)
        secret = decrypt_json(row.key_nonce, row.key_ciphertext)
        private = str(secret.get("private_key") or "")
        try:
            tx = sign_transfer(private, row.public_key, row.address, recipient, units, ledger.params.fee, ledger.next_nonce(row.address))
            ledger.add_transfer(tx)
        except ChainError as exc:
            raise ChainServiceError(400, str(exc)) from exc
        finally:
            private = ""
        db.add(_tx_row(org_id, tx.tx_hash(), "transfer", tx.sender, tx.recipient, tx.amount, tx.fee, tx.nonce, tx.public_key, tx.signature, None))
        db.commit()
    logger.info("chain_transfer_queued org=%s tx=%s", org_id, tx.tx_hash())
    return {"tx_hash": tx.tx_hash(), "status": "pending", "amount": format_amount(units), "fee": format_amount(ledger.params.fee)}


def list_blocks(db: Session, org_id, limit: int = 50) -> list[dict]:
    ledger = load_ledger(db, org_id)
    rows = list(reversed(ledger.blocks))[: max(1, min(limit, 200))]
    return [_public_block(block) for block in rows]


def block_detail(db: Session, org_id, height: int) -> dict:
    ledger = load_ledger(db, org_id)
    for block in ledger.blocks:
        if block.index == height:
            detail = _public_block(block)
            detail["transactions"] = _public_transactions(block)
            detail["confirmations"] = ledger.height() - block.index + 1
            return detail
    raise ChainServiceError(404, "No block at that height")


def block_by_hash(db: Session, org_id, digest: str) -> dict:
    ledger = load_ledger(db, org_id)
    for block in ledger.blocks:
        if block.block_hash() == digest:
            return block_detail(db, org_id, block.index)
    raise ChainServiceError(404, "No block with that hash")


def list_transactions(db: Session, org_id, limit: int = 50) -> list[dict]:
    ledger = load_ledger(db, org_id)
    items = []
    for block in reversed(ledger.blocks):
        items.extend(_public_transactions(block, confirmations=ledger.height() - block.index + 1))
        if len(items) >= limit:
            break
    for tx in reversed(ledger.pending):
        items.append(_public_transfer(tx, None, 0))
    return items[:limit]


def transaction_detail(db: Session, org_id, tx_hash: str) -> dict:
    for item in list_transactions(db, org_id, limit=5000):
        if item["tx_hash"] == tx_hash:
            return item
    raise ChainServiceError(404, "No transaction with that hash")


def wallet_transactions(db: Session, org_id, user_id) -> list[dict]:
    row = _require_wallet(db, org_id, user_id)
    return [item for item in list_transactions(db, org_id, limit=200) if item["sender"] == row.address or item["recipient"] == row.address]


def search(db: Session, org_id, query: str) -> dict:
    text = query.strip().lower()
    ledger = load_ledger(db, org_id)
    if text.isdigit():
        try:
            return {"kind": "block", "block": block_detail(db, org_id, int(text))}
        except ChainServiceError:
            return {"kind": "none"}
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text):
        for block in ledger.blocks:
            if block.block_hash() == text:
                return {"kind": "block", "block": block_detail(db, org_id, block.index)}
        try:
            return {"kind": "transaction", "transaction": transaction_detail(db, org_id, text)}
        except ChainServiceError:
            return {"kind": "none"}
    if ADDRESS.match(text):
        balances, _, _ = ledger.state()
        totals = ledger.totals(text)
        txs = [item for item in list_transactions(db, org_id, limit=200) if item["sender"] == text or item["recipient"] == text]
        return {
            "kind": "wallet",
            "wallet": {
                "address": text,
                "available": format_amount(balances.get(text, 0)),
                "pending": format_amount(ledger.pending_incoming(text)),
                "mined": format_amount(totals["mined"]),
                "received": format_amount(totals["received"]),
                "sent": format_amount(totals["sent"]),
                "transactions": txs,
            },
        }
    return {"kind": "none"}


def network_status(db: Session, org_id) -> dict:
    ledger = load_ledger(db, org_id)
    node_key = hashlib.sha256(f"maestro-local:{org_id}".encode()).hexdigest()[:16]
    row = db.scalar(select(ChainNode).where(ChainNode.organization_id == org_id, ChainNode.node_key == node_key))
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(ChainNode(organization_id=org_id, node_key=node_key, label="this computer", status="online", last_seen=now))
    else:
        row.last_seen = now
        row.status = "online"
    db.commit()
    return {
        "mode": "single-node",
        "decentralized": False,
        "detail": "This chain runs on this Maestro server. It is not a public network.",
        "node_id": node_key,
        "peers": [],
        "height": ledger.height(),
        "difficulty": ledger.params.difficulty,
        "work": ledger.work(),
        "coin": _params_row(ledger.params),
    }


def _public_block(block: Block) -> dict:
    earned = block.reward_tx.amount if block.reward_tx is not None else 0
    return {
        "height": block.index,
        "timestamp": block.timestamp,
        "previous_hash": block.previous_hash,
        "hash": block.block_hash(),
        "nonce": block.nonce,
        "difficulty": block.difficulty,
        "miner": block.miner,
        "reward": format_amount(block.reward),
        "earned": format_amount(earned),
        "transactions": len(block.transfers) + (1 if block.reward_tx else 0),
    }


def _public_transfer(tx: Transfer, height: int | None, confirmations: int) -> dict:
    return {
        "tx_hash": tx.tx_hash(),
        "kind": "transfer",
        "sender": tx.sender,
        "recipient": tx.recipient,
        "amount": format_amount(tx.amount),
        "fee": format_amount(tx.fee),
        "nonce": tx.nonce,
        "block_height": height,
        "confirmations": confirmations,
        "status": "confirmed" if height is not None else "pending",
    }


def _public_transactions(block: Block, confirmations: int = 1) -> list[dict]:
    rows = [_public_transfer(tx, block.index, confirmations) for tx in block.transfers]
    if block.reward_tx is not None:
        rows.append(
            {
                "tx_hash": block.reward_tx.tx_hash(),
                "kind": "reward",
                "sender": "",
                "recipient": block.reward_tx.recipient,
                "amount": format_amount(block.reward_tx.amount),
                "fee": "0",
                "nonce": 0,
                "block_height": block.index,
                "confirmations": confirmations,
                "status": "confirmed",
            }
        )
    return rows


def _clamp_cpu(value: int | None) -> int:
    settings = get_settings()
    chosen = settings.chain_cpu_percent if value is None else int(value)
    return max(5, min(chosen, settings.chain_cpu_max))


def _control_key(org_id, user_id) -> tuple[str, str]:
    return str(org_id), str(user_id)


def _mine_round(stop, pause, control: MinerControl, org_id, user_id, cpu: int):
    if stop.is_set() or pause.is_set():
        return None
    db = SessionLocal()
    try:
        wallet = _require_wallet(db, org_id, user_id)
        address = wallet.address
        with _lock(org_id):
            ledger = load_ledger(db, org_id)
            block = ledger.candidate(address, int(time.time()))
    except ChainServiceError:
        return None
    finally:
        db.close()
    found, hashes = mine_in_process(block, cpu, stop, pause)
    control.note_hashes(hashes)
    if found is None or stop.is_set() or pause.is_set():
        return None
    block.nonce = found[0]
    if block.block_hash() != found[1]:
        return None
    db = SessionLocal()
    try:
        with _lock(org_id):
            ledger = load_ledger(db, org_id)
            try:
                ledger.accept(block)
            except ChainError:
                logger.info("chain_block_rejected org=%s height=%s", org_id, block.index)
                return None
            _insert_block(db, org_id, block)
            earned = block.reward_tx.amount if block.reward_tx is not None else 0
            db.add(ChainHit(organization_id=org_id, user_id=user_id, height=block.index, block_hash=block.block_hash(), reward=earned, hashes=hashes))
            db.commit()
        logger.info("chain_block_accepted org=%s height=%s", org_id, block.index)
        return block.block_hash()
    except Exception:
        db.rollback()
        logger.exception("chain_block_store_failed")
        return None
    finally:
        db.close()


def start_mining(db: Session, org_id, user_id, cpu_percent: int | None) -> dict:
    _require_wallet(db, org_id, user_id)
    cpu = _clamp_cpu(cpu_percent)
    key = _control_key(org_id, user_id)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
        if control is None or control.status == "stopped":
            control = MinerControl(lambda stop, pause, ctl: _mine_round(stop, pause, ctl, org_id, user_id, cpu), cpu)
            _CONTROLS[key] = control
            control.start()
            db.add(ChainSessionRow(organization_id=org_id, user_id=user_id, status="running", difficulty=coin_params().difficulty, cpu_percent=cpu))
            db.commit()
        elif control.status == "paused":
            control.resume()
    return mining_status(db, org_id, user_id)


def stop_mining(db: Session, org_id, user_id) -> dict:
    key = _control_key(org_id, user_id)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
    if control is not None:
        control.stop()
    _close_session(db, org_id, user_id, "stopped")
    return mining_status(db, org_id, user_id)


def pause_mining(db: Session, org_id, user_id) -> dict:
    key = _control_key(org_id, user_id)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
    if control is None or control.status == "stopped":
        raise ChainServiceError(409, "Mining is not running")
    control.pause()
    return mining_status(db, org_id, user_id)


def resume_mining(db: Session, org_id, user_id) -> dict:
    key = _control_key(org_id, user_id)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
    if control is None or control.status != "paused":
        raise ChainServiceError(409, "Mining is not paused")
    control.resume()
    return mining_status(db, org_id, user_id)


def _close_session(db: Session, org_id, user_id, status: str) -> None:
    row = db.scalar(select(ChainSessionRow).where(ChainSessionRow.organization_id == org_id, ChainSessionRow.user_id == user_id, ChainSessionRow.stopped_at.is_(None)).order_by(ChainSessionRow.started_at.desc()))
    if row is not None:
        row.status = status
        row.stopped_at = datetime.now(timezone.utc)
        db.commit()


def mining_status(db: Session, org_id, user_id) -> dict:
    ledger = load_ledger(db, org_id)
    wallet = _wallet(db, org_id, user_id)
    key = _control_key(org_id, user_id)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
    status = control.status if control is not None else "stopped"
    address = wallet.address if wallet is not None else ""
    totals = ledger.totals(address) if address else {"mined": 0, "received": 0, "sent": 0}
    blocks_mined = sum(1 for block in ledger.blocks if block.miner == address)
    latest = next((block for block in reversed(ledger.blocks) if block.miner == address), None)
    return {
        "status": status,
        "hashrate": round(control.hashrate, 2) if control else 0,
        "hashes": control.hashes if control else 0,
        "duration_seconds": round(control.duration(), 1) if control else 0,
        "difficulty": ledger.params.difficulty,
        "height": ledger.height(),
        "current_block": (ledger.height() + 1) if status in {"running", "paused"} else None,
        "success": control.success if control else 0,
        "failed": control.failed if control else 0,
        "blocks_mined": blocks_mined,
        "rewards": format_amount(totals["mined"]),
        "cpu_percent": control.cpu_percent if control else 0,
        "last_block_hash": latest.block_hash() if latest else "",
        "last_reward": format_amount(latest.reward_tx.amount) if latest and latest.reward_tx else "0",
        "network_hashrate": round(control.hashrate, 2) if control else 0,
        "network_scope": "this-node-only",
        "symbol": ledger.params.symbol,
        "coin": _params_row(ledger.params),
    }


def mining_statistics(db: Session, org_id, user_id) -> dict:
    status = mining_status(db, org_id, user_id)
    hits = list(db.scalars(select(ChainHit).where(ChainHit.organization_id == org_id, ChainHit.user_id == user_id).order_by(ChainHit.found_at.desc()).limit(20)))
    status["history"] = [
        {"height": hit.height, "hash": hit.block_hash, "reward": format_amount(int(hit.reward)), "hashes": int(hit.hashes), "found_at": hit.found_at.isoformat()}
        for hit in hits
    ]
    sessions = list(db.scalars(select(ChainSessionRow).where(ChainSessionRow.organization_id == org_id, ChainSessionRow.user_id == user_id).order_by(ChainSessionRow.started_at.desc()).limit(10)))
    status["sessions"] = [{"status": row.status, "cpu_percent": row.cpu_percent, "started_at": row.started_at.isoformat(), "stopped_at": row.stopped_at.isoformat() if row.stopped_at else None} for row in sessions]
    return status


def sync_chain(local: Ledger, remote: Ledger) -> Ledger:
    """Keep the chain with more validated work. Used by tests and a future peer link."""
    local.replace_if_stronger(remote)
    return local
