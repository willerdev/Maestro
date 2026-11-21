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
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chain.crypto import ADDRESS, address_for, new_keypair, public_from_private
from app.chain.ledger import Block, ChainError, CoinParams, Ledger, Reward, Transfer, sign_transfer
from app.chain.miner import MinerControl, mine_in_process
from app.chain.money import UNIT, format_amount, parse_amount
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.encryption import decrypt_json, encrypt_json
from app.models.chain_entities import ChainBlockRow, ChainHit, ChainNode, ChainSessionRow, ChainTxRow, ChainWallet, MiningComputer, MiningRewardLedger
from app.models.entities import LicenseKey, User
from app.services.license_service import computer_name, mining_device_hash

logger = logging.getLogger(__name__)

_ORG_LOCKS: dict[str, threading.Lock] = {}
_CONTROLS: dict[tuple[str, str, str], MinerControl] = {}
_CPU_PREF: dict[tuple[str, str, str], int] = {}
_CONTROL_LOCK = threading.Lock()
MAX_DEVICE_MINERS = 5


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
    from app.services.conversion_service import pcoin_hold, usdt_balance, public_settings
    from app.chain.convert import format_usdt

    held = pcoin_hold(db, org_id, user_id)
    from app.services.mining_plan_service import bonus_available

    bonus = bonus_available(db, org_id, user_id)
    from app.services.pcoin_approval_service import held_pcoin_atomic

    spendable = max(0, ledger.available(row.address) - held + bonus - held_pcoin_atomic(db, org_id, user_id))
    rules = public_settings(db, org_id)
    from app.services.asset_service import _available

    owner = db.get(User, user_id)
    cash = Decimal("0")
    if owner is not None:
        cash = _available(db, owner, "usdttrc20") + _available(db, owner, "usdt")
    return {
        "address": row.address,
        "public_key": row.public_key,
        "available": format_amount(spendable),
        "confirmed": format_amount(balances.get(row.address, 0)),
        "pending": format_amount(ledger.pending_incoming(row.address)),
        "mined": format_amount(totals["mined"] + bonus),
        "received": format_amount(totals["received"]),
        "sent": format_amount(totals["sent"]),
        "withdrawn": format_amount(totals["sent"]),
        "lifetime_earnings": format_amount(totals["mined"] + bonus),
        "pending_rewards": "0",
        "premium_available": format_amount(bonus),
        "pow_mined": format_amount(totals["mined"]),
        "market_value": None,
        "converted": format_amount(held),
        "usdt_available": format(cash.quantize(Decimal("0.01")), "f"),
        "usdt_total": format_usdt(usdt_balance(db, org_id, user_id)),
        "exchange_rate": rules["rate"],
        "exchange_label": rules["label"],
        "confirmation_rule": "New Project Coin is spendable after an admin approves it. Converted PCoin is reserved and cannot be sent.",
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
        raise ChainServiceError(400, "Enter a Project Coin address that starts with pcoin1")
    if recipient == row.address:
        raise ChainServiceError(400, "You cannot send PCoin to your own address")
    try:
        units = parse_amount(amount)
    except ValueError as exc:
        raise ChainServiceError(400, str(exc)) from exc
    with _lock(org_id):
        ledger = load_ledger(db, org_id)
        from app.services.conversion_service import pcoin_hold

        if units + ledger.params.fee > max(0, ledger.available(row.address) - pcoin_hold(db, org_id, user_id)):
            raise ChainServiceError(400, "The PCoin balance is too low")
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
        "detail": "Project Coin runs on this Maestro server. This computer is the only node.",
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
        "timestamp": None,
    }


def _public_transactions(block: Block, confirmations: int = 1) -> list[dict]:
    rows = [_public_transfer(tx, block.index, confirmations) for tx in block.transfers]
    for row in rows:
        row["timestamp"] = block.timestamp
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
                "timestamp": block.timestamp,
            }
        )
    return rows


def _clamp_cpu(value: int | None) -> int:
    settings = get_settings()
    chosen = settings.chain_cpu_percent if value is None else int(value)
    return max(5, min(chosen, settings.chain_cpu_max))


def _control_key(org_id, user_id, device_hash: str = "") -> tuple[str, str, str]:
    return str(org_id), str(user_id), device_hash or "_"


def _controls_for_user(org_id, user_id) -> list[tuple[tuple[str, str, str], MinerControl]]:
    org, user = str(org_id), str(user_id)
    with _CONTROL_LOCK:
        return [(key, control) for key, control in _CONTROLS.items() if key[0] == org and key[1] == user]


def user_mining_running(org_id, user_id) -> bool:
    return any(control.status == "running" for _key, control in _controls_for_user(org_id, user_id))


def running_device_hashes(org_id, user_id) -> list[str]:
    return [key[2] for key, control in _controls_for_user(org_id, user_id) if control.status == "running"]


def touch_computer(db: Session, org_id, user_id, device_hash: str, user_agent: str = "") -> MiningComputer:
    now = datetime.now(timezone.utc)
    row = db.scalar(select(MiningComputer).where(MiningComputer.user_id == user_id, MiningComputer.device_hash == device_hash))
    label = computer_name(user_agent, device_hash)
    if row is None:
        row = MiningComputer(
            id=uuid4(),
            organization_id=org_id,
            user_id=user_id,
            device_hash=device_hash,
            label=label,
            user_agent=(user_agent or "")[:300],
            last_seen=now,
        )
        db.add(row)
    else:
        row.last_seen = now
        if user_agent:
            row.user_agent = user_agent[:300]
            row.label = label
    db.flush()
    return row


def list_mining_computers(db: Session, org_id, user_id, current_hash: str = "") -> list[dict]:
    hashes: set[str] = set()
    rows = list(db.scalars(select(MiningComputer).where(MiningComputer.organization_id == org_id, MiningComputer.user_id == user_id)).all())
    by_hash = {row.device_hash: row for row in rows}
    hashes.update(by_hash)
    for key, _control in _controls_for_user(org_id, user_id):
        hashes.add(key[2])
    for hit_hash in db.scalars(select(ChainHit.device_hash).where(ChainHit.organization_id == org_id, ChainHit.user_id == user_id, ChainHit.device_hash != "")).all():
        hashes.add(hit_hash)
    for license_hash in db.scalars(select(LicenseKey.device_hash).where(LicenseKey.user_id == user_id, LicenseKey.status == "used", LicenseKey.device_hash != "")).all():
        hashes.add(license_hash)
    hashes.discard("")
    hashes.discard("_")
    live = {key[2]: control for key, control in _controls_for_user(org_id, user_id)}
    pow_map = {
        device: int(total or 0)
        for device, total in db.execute(
            select(ChainHit.device_hash, func.coalesce(func.sum(ChainHit.reward), 0)).where(
                ChainHit.organization_id == org_id,
                ChainHit.user_id == user_id,
            ).group_by(ChainHit.device_hash)
        ).all()
    }
    premium_map = {
        device: int(total or 0)
        for device, total in db.execute(
            select(MiningRewardLedger.device_hash, func.coalesce(func.sum(MiningRewardLedger.amount_atomic), 0)).where(
                MiningRewardLedger.organization_id == org_id,
                MiningRewardLedger.user_id == user_id,
                MiningRewardLedger.amount_atomic > 0,
            ).group_by(MiningRewardLedger.device_hash)
        ).all()
    }
    computers = []
    for device_hash in hashes:
        row = by_hash.get(device_hash)
        control = live.get(device_hash)
        pow_atomic = pow_map.get(device_hash, 0)
        premium_atomic = premium_map.get(device_hash, 0)
        status = control.status if control is not None else "stopped"
        computers.append(
            {
                "id": device_hash[:12],
                "label": row.label if row else computer_name("", device_hash),
                "this_computer": device_hash == current_hash,
                "status": status,
                "hashrate": round(control.hashrate, 2) if control and status == "running" else 0,
                "pow_mined": format_amount(pow_atomic),
                "premium": format_amount(premium_atomic),
                "earned": format_amount(pow_atomic + premium_atomic),
                "last_seen": row.last_seen.isoformat() if row and row.last_seen else "",
            }
        )
    computers.sort(key=lambda item: (0 if item["this_computer"] else 1, 0 if item["status"] == "running" else 1, item["label"]))
    return computers


def list_org_mining_computers(db: Session, org_id, current_user_id=None, current_hash: str = "") -> list[dict]:
    users = {row.id: row for row in db.scalars(select(User).where(User.organization_id == org_id)).all()}
    groups = []
    for user in sorted(users.values(), key=lambda item: item.email):
        computers = list_mining_computers(db, org_id, user.id, current_hash if current_user_id == user.id else "")
        if not computers:
            continue
        groups.append(
            {
                "user_id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "computers": computers,
            }
        )
    return groups


def remaining_daily_atomic(db: Session, org_id, user_id) -> int | None:
    """Atomic PCoin still allowed today. None means this login has no daily cap."""
    from app.models.chain_entities import UserEarningCap
    from app.services.conversion_service import public_settings

    row = db.get(UserEarningCap, user_id)
    if row is None or row.daily_usdt <= 0:
        return None
    rate = Decimal(str(public_settings(db, org_id)["rate"]))
    cap = int((Decimal(row.daily_usdt) * rate * Decimal(UNIT)).to_integral_value(rounding=ROUND_DOWN))
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    mined = db.scalar(
        select(func.coalesce(func.sum(ChainHit.reward), 0)).where(
            ChainHit.organization_id == org_id,
            ChainHit.user_id == user_id,
            ChainHit.found_at >= start,
        )
    )
    bonus = db.scalar(
        select(func.coalesce(func.sum(MiningRewardLedger.amount_atomic), 0)).where(
            MiningRewardLedger.organization_id == org_id,
            MiningRewardLedger.user_id == user_id,
            MiningRewardLedger.amount_atomic > 0,
            MiningRewardLedger.created_at >= start,
        )
    )
    return max(0, cap - int(mined or 0) - int(bonus or 0))


def _mine_round(stop, pause, control: MinerControl, org_id, user_id, cpu: int, device_hash: str = ""):
    if stop.is_set() or pause.is_set():
        return None
    db = SessionLocal()
    try:
        from app.services.mining_plan_service import mining_paused

        if mining_paused(db, org_id):
            time.sleep(1)
            return None
        room = remaining_daily_atomic(db, org_id, user_id)
        if room is not None and room <= 0:
            time.sleep(30)
            return None
    finally:
        db.close()
    db = SessionLocal()
    try:
        wallet = _require_wallet(db, org_id, user_id)
        address = wallet.address
        with _lock(org_id):
            ledger = load_ledger(db, org_id)
            block = ledger.candidate(address, int(time.time()))
        room = remaining_daily_atomic(db, org_id, user_id)
        if room is not None and block.reward > room:
            time.sleep(30)
            return None
    except ChainServiceError:
        return None
    finally:
        db.close()
    found, hashes = mine_in_process(block, control.cpu_percent, stop, pause)
    control.note_hashes(hashes)
    if found is None or stop.is_set() or pause.is_set():
        return None
    block.nonce = found[0]
    if block.block_hash() != found[1]:
        return None
    db = SessionLocal()
    try:
        room = remaining_daily_atomic(db, org_id, user_id)
        if room is not None and block.reward > room:
            time.sleep(30)
            return None
    finally:
        db.close()
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
            db.add(ChainHit(organization_id=org_id, user_id=user_id, height=block.index, block_hash=block.block_hash(), reward=earned, hashes=hashes, device_hash=device_hash))
            db.commit()
        logger.info("chain_block_accepted org=%s height=%s", org_id, block.index)
        return block.block_hash()
    except Exception:
        db.rollback()
        logger.exception("chain_block_store_failed")
        return None
    finally:
        db.close()


def resume_capped_miners(db: Session) -> None:
    """Keep a capped Project Coin miner running inside this API process."""
    from app.models.chain_entities import UserEarningCap

    rows = list(db.scalars(select(UserEarningCap)).all())
    for row in rows:
        try:
            start_mining(db, row.organization_id, row.user_id, 30, "maestro-server", "maestro")
        except ChainServiceError as exc:
            logger.info("capped_miner_not_started user=%s detail=%s", row.user_id, exc.detail)


def start_mining(db: Session, org_id, user_id, cpu_percent: int | None, device_id: str = "", user_agent: str = "") -> dict:
    from app.services.mining_plan_service import MiningPlanError, arm_accrual, assert_mining_allowed

    try:
        assert_mining_allowed(db, org_id)
    except MiningPlanError as exc:
        raise ChainServiceError(exc.status, exc.detail) from exc
    _require_wallet(db, org_id, user_id)
    device_hash = mining_device_hash(device_id)
    touch_computer(db, org_id, user_id, device_hash, user_agent)
    key = _control_key(org_id, user_id, device_hash)
    cpu = _clamp_cpu(cpu_percent if cpu_percent is not None else _CPU_PREF.get(key))
    _CPU_PREF[key] = cpu
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
        active = [
            item
            for item_key, item in _CONTROLS.items()
            if item_key[0] == str(org_id) and item_key[1] == str(user_id) and item.status in {"running", "paused"}
        ]
        if control is None or control.status == "stopped":
            if len(active) >= MAX_DEVICE_MINERS:
                raise ChainServiceError(409, "Stop mining on another computer first. Up to 5 computers can mine on this login.")
            control = MinerControl(lambda stop, pause, ctl: _mine_round(stop, pause, ctl, org_id, user_id, cpu, device_hash), cpu)
            _CONTROLS[key] = control
            control.start()
            db.add(
                ChainSessionRow(
                    organization_id=org_id,
                    user_id=user_id,
                    status="running",
                    difficulty=coin_params().difficulty,
                    cpu_percent=cpu,
                    device_hash=device_hash,
                )
            )
            arm_accrual(db, org_id, user_id)
            db.commit()
        elif control.status == "paused":
            control.resume()
            arm_accrual(db, org_id, user_id)
    return mining_status(db, org_id, user_id, device_id, user_agent)


def stop_mining(db: Session, org_id, user_id, device_id: str = "", user_agent: str = "") -> dict:
    from app.services.mining_plan_service import flush_accrual

    flush_accrual(db, org_id, user_id)
    device_hash = mining_device_hash(device_id)
    key = _control_key(org_id, user_id, device_hash)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
    if control is not None:
        control.stop()
    _close_session(db, org_id, user_id, "stopped", device_hash)
    return mining_status(db, org_id, user_id, device_id, user_agent)


def pause_mining(db: Session, org_id, user_id, device_id: str = "", user_agent: str = "") -> dict:
    device_hash = mining_device_hash(device_id)
    key = _control_key(org_id, user_id, device_hash)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
    if control is None or control.status == "stopped":
        raise ChainServiceError(409, "Mining is not running on this computer")
    from app.services.mining_plan_service import flush_accrual

    flush_accrual(db, org_id, user_id)
    control.pause()
    return mining_status(db, org_id, user_id, device_id, user_agent)


def resume_mining(db: Session, org_id, user_id, device_id: str = "", user_agent: str = "") -> dict:
    device_hash = mining_device_hash(device_id)
    key = _control_key(org_id, user_id, device_hash)
    with _CONTROL_LOCK:
        control = _CONTROLS.get(key)
    if control is None or control.status != "paused":
        raise ChainServiceError(409, "Mining is not paused on this computer")
    from app.services.mining_plan_service import arm_accrual

    control.resume()
    arm_accrual(db, org_id, user_id)
    return mining_status(db, org_id, user_id, device_id, user_agent)


def _close_session(db: Session, org_id, user_id, status: str, device_hash: str = "") -> None:
    query = select(ChainSessionRow).where(
        ChainSessionRow.organization_id == org_id,
        ChainSessionRow.user_id == user_id,
        ChainSessionRow.stopped_at.is_(None),
    )
    if device_hash:
        query = query.where(ChainSessionRow.device_hash == device_hash)
    row = db.scalar(query.order_by(ChainSessionRow.started_at.desc()))
    if row is not None:
        row.status = status
        row.stopped_at = datetime.now(timezone.utc)
        db.commit()


def mining_status(db: Session, org_id, user_id, device_id: str = "", user_agent: str = "") -> dict:
    from app.services.mining_plan_service import accrue_user, hybrid_overview

    accrue_user(db, org_id, user_id)
    ledger = load_ledger(db, org_id)
    wallet = _wallet(db, org_id, user_id)
    device_hash = mining_device_hash(device_id) if device_id else mining_device_hash("")
    if device_id:
        touch_computer(db, org_id, user_id, device_hash, user_agent)
    key = _control_key(org_id, user_id, device_hash)
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
        "cpu_percent": control.cpu_percent if control is not None and control.status != "stopped" else _CPU_PREF.get(key, get_settings().chain_cpu_percent),
        "last_block_hash": latest.block_hash() if latest else "",
        "last_reward": format_amount(latest.reward_tx.amount) if latest and latest.reward_tx else "0",
        "network_hashrate": round(control.hashrate, 2) if control else 0,
        "network_scope": "this-node-only",
        "symbol": ledger.params.symbol,
        "coin": _params_row(ledger.params),
        "hashrate_samples": list(control.samples) if control else [],
        "hybrid": hybrid_overview(db, org_id, user_id),
        "this_computer": device_hash[:6],
        "computers": list_mining_computers(db, org_id, user_id, device_hash),
    }


def mining_statistics(db: Session, org_id, user_id, device_id: str = "", user_agent: str = "") -> dict:
    status = mining_status(db, org_id, user_id, device_id, user_agent)
    hits = list(db.scalars(select(ChainHit).where(ChainHit.organization_id == org_id, ChainHit.user_id == user_id).order_by(ChainHit.found_at.desc()).limit(20)))
    status["history"] = [
        {"height": hit.height, "hash": hit.block_hash, "reward": format_amount(int(hit.reward)), "hashes": int(hit.hashes), "found_at": hit.found_at.isoformat()}
        for hit in hits
    ]
    sessions = list(db.scalars(select(ChainSessionRow).where(ChainSessionRow.organization_id == org_id, ChainSessionRow.user_id == user_id).order_by(ChainSessionRow.started_at.desc()).limit(10)))
    status["sessions"] = [{"status": row.status, "cpu_percent": row.cpu_percent, "started_at": row.started_at.isoformat(), "stopped_at": row.stopped_at.isoformat() if row.stopped_at else None} for row in sessions]
    return status


def set_cpu(db: Session, org_id, user_id, cpu_percent: int, device_id: str = "", user_agent: str = "") -> dict:
    cpu = _clamp_cpu(cpu_percent)
    key = _control_key(org_id, user_id, mining_device_hash(device_id))
    with _CONTROL_LOCK:
        _CPU_PREF[key] = cpu
        control = _CONTROLS.get(key)
    if control is not None:
        control.cpu_percent = cpu
    return mining_status(db, org_id, user_id, device_id, user_agent)


def _span_start(span: str) -> int | None:
    now = int(time.time())
    if span == "24h":
        return now - 24 * 3600
    if span == "7d":
        return now - 7 * 24 * 3600
    if span == "30d":
        return now - 30 * 24 * 3600
    return None


def _activity_rows(ledger: Ledger, address: str) -> list[dict]:
    rows: list[dict] = []
    for block in ledger.blocks:
        for item in _public_transactions(block, confirmations=ledger.height() - block.index + 1):
            if item["kind"] == "reward" and item["recipient"] == address:
                item["type"] = "mining_reward"
                rows.append(item)
            elif item["kind"] == "transfer" and item["recipient"] == address:
                item["type"] = "incoming"
                rows.append(item)
            elif item["kind"] == "transfer" and item["sender"] == address:
                item["type"] = "outgoing"
                rows.append(item)
                if item["fee"] != "0":
                    fee = dict(item)
                    fee["type"] = "network_fee"
                    fee["amount"] = item["fee"]
                    rows.append(fee)
    for tx in ledger.pending:
        if tx.sender != address and tx.recipient != address:
            continue
        item = _public_transfer(tx, None, 0)
        item["type"] = "outgoing" if tx.sender == address else "incoming"
        rows.append(item)
    rows.reverse()
    return rows


def account_activity(db: Session, org_id, user_id, span: str = "all", kind: str = "all", query: str = "", limit: int = 25, offset: int = 0) -> dict:
    row = _require_wallet(db, org_id, user_id)
    ledger = load_ledger(db, org_id)
    start = _span_start(span)
    text = query.strip().lower()
    matched = []
    for item in _activity_rows(ledger, row.address):
        if kind != "all" and item.get("type") != kind:
            continue
        if start is not None and item.get("timestamp") not in (None, 0) and int(item["timestamp"]) < start:
            continue
        blob = f"{item.get('tx_hash','')} {item.get('sender','')} {item.get('recipient','')}".lower()
        if text and text not in blob:
            continue
        matched.append(item)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return {"total": len(matched), "items": matched[offset:offset + limit]}


def dashboard(db: Session, org_id, user_id, span: str = "all", device_id: str = "", user_agent: str = "") -> dict:
    wallet = _wallet(db, org_id, user_id)
    status = mining_status(db, org_id, user_id, device_id, user_agent)
    ledger = load_ledger(db, org_id)
    address = wallet.address if wallet is not None else ""
    view = None
    if wallet is not None:
        view = wallet_view(db, org_id, user_id)
    start = _span_start(span)
    rewards = []
    balance_points = []
    daily: dict[str, int] = {}
    running = 0
    for block in ledger.blocks:
        delta = 0
        if address and block.reward_tx is not None and block.reward_tx.recipient == address:
            delta += block.reward_tx.amount
        for tx in block.transfers:
            if not address:
                break
            if tx.recipient == address:
                delta += tx.amount
            if tx.sender == address:
                delta -= tx.amount + tx.fee
        running += delta
        if start is not None and block.timestamp < start:
            continue
        balance_points.append({"t": block.timestamp, "balance": format_amount(running)})
        if address and block.miner == address and block.reward_tx is not None:
            rewards.append(
                {
                    "height": block.index,
                    "hash": block.block_hash(),
                    "miner": block.miner,
                    "reward": format_amount(block.reward_tx.amount),
                    "subsidy": format_amount(block.reward),
                    "timestamp": block.timestamp,
                    "status": "confirmed",
                    "tx_hash": block.reward_tx.tx_hash(),
                    "confirmations": ledger.height() - block.index + 1,
                }
            )
            day = datetime.fromtimestamp(block.timestamp, timezone.utc).date().isoformat()
            daily[day] = daily.get(day, 0) + 1
    samples = [point for point in status.get("hashrate_samples", []) if start is None or point["t"] >= start]
    return {
        "span": span if span in {"24h", "7d", "30d", "all"} else "all",
        "market_value": None,
        "market_value_label": "unavailable",
        "network_mode": "single-node",
        "network_detail": "Project Coin runs on this Maestro server. This computer is the only node.",
        "wallet": view,
        "mining": status,
        "hybrid": status.get("hybrid"),
        "rewards": list(reversed(rewards))[:50],
        "series": {
            "rewards": [{"t": item["timestamp"], "amount": item["reward"]} for item in rewards],
            "hashrate": samples,
            "blocks_per_day": [{"day": day, "count": daily[day]} for day in sorted(daily)],
            "balance": balance_points,
        },
    }


def sync_chain(local: Ledger, remote: Ledger) -> Ledger:
    """Keep the chain with more validated work. Used by tests and a future peer link."""
    local.replace_if_stronger(remote)
    return local
