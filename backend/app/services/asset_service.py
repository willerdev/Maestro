from __future__ import annotations

import re
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.payments import PaymentProviderError, connector_for
from app.core.encryption import decrypt_json
from app.domain.audit import write_audit
from app.models.entities import AssetTransfer, Organization, PaymentProviderConfig, User
from app.services.payment_service import PaymentError, _callback_url, _public_wallet_detail, create_payment

CREDIT_PURPOSES = {
    "earnings": "Earnings",
    "mining_rewards": "Mining rewards",
    "blockchain_rewards": "Blockchain rewards",
    "trading_profit": "Trading profit",
    "contract_yield": "Contract yield",
    "bonus": "Bonus",
    "referral": "Referral",
    "adjustment": "Adjustment",
}
_CREDIT_ALIASES = {
    "earning": "earnings",
    "mining": "mining_rewards",
    "mining_reward": "mining_rewards",
    "blockchain": "blockchain_rewards",
    "blockchain_reward": "blockchain_rewards",
    "trading": "trading_profit",
    "contract": "contract_yield",
    "yield": "contract_yield",
}

_COIN = re.compile(r"^[A-Za-z0-9]{2,20}$")
_ADDRESS = re.compile(r"^[A-Za-z0-9]{26,128}$")
_SCALE = Decimal("0.00000001")
_MAX = Decimal("1000000000000")
_POSTED = {"finished", "completed", "success"}
_FAILED = {"failed", "rejected", "expired", "refunded"}
_HELD_WITHDRAW = {"requested", "pending", "posted", "paused"}
_OPEN_WITHDRAW = {"requested", "pending"}


class AssetError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def credit_purpose(code: object) -> tuple[str, str]:
    raw = str(code or "earnings").strip().lower().replace(" ", "_").replace("-", "_")
    key = _CREDIT_ALIASES.get(raw, raw) or "earnings"
    label = CREDIT_PURPOSES.get(key)
    if not label:
        raise AssetError(400, "Choose what this credit is for")
    return key, label


def credit_label(row: AssetTransfer) -> tuple[str, str]:
    code = str(row.provider_id or "").strip().lower()
    if code in CREDIT_PURPOSES:
        return code, CREDIT_PURPOSES[code]
    note = str(row.note or "").strip()
    if row.direction == "deposit" and (note in {"Wallet credit", "Earnings"} or str(row.order_id or "").startswith("AD")):
        return "earnings", "Earnings"
    for key, label in CREDIT_PURPOSES.items():
        if note == label:
            return key, label
    return "", ""


def asset_home(db: Session, user: User) -> dict:
    config = _nowpayments(db, user, required=False)
    return {
        "configured": config is not None,
        "provider": "" if config is None else config.provider,
        "balances": _balances(db, user),
        "transfers": [_payload(row) for row in _rows(db, user)],
    }


def request_deposit(db: Session, user: User, currency: str, amount: Decimal, ip: str, *, client: httpx.Client | None = None) -> dict:
    _nowpayments(db, user, required=True)
    coin = _coin(currency or "usdttrc20")
    cash = _crypto(amount)
    try:
        payment = create_payment(
            db,
            user,
            {
                "price_amount": cash,
                "price_currency": coin,
                "pay_currency": coin,
                "purpose": "deposit",
                "description": f"USDT TRC20 deposit" if coin == "usdttrc20" else f"Asset deposit {coin}",
            },
            ip,
            client=client,
            amount_scale=_SCALE,
        )
    except PaymentError as exc:
        raise AssetError(exc.status, exc.detail) from exc
    row = AssetTransfer(
        organization_id=user.organization_id,
        user_id=user.id,
        currency=coin,
        direction="deposit",
        amount=cash,
        status="pending",
        address=str(payment.get("pay_address") or ""),
        provider_id=str(payment.get("provider_payment_id") or ""),
        order_id=str(payment.get("order_id") or ""),
        invoice_url=str(payment.get("invoice_url") or ""),
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="asset_deposit_requested",
        entity_type="asset_transfer",
        entity_id=str(row.id),
        after={"currency": coin, "amount": format(cash, "f"), "status": "pending"},
        ip_address=ip,
    )
    return _payload(row)


def request_withdrawal(db: Session, user: User, currency: str, amount: Decimal, address: str, ip: str, *, client: httpx.Client | None = None) -> dict:
    _nowpayments(db, user, required=True)
    coin = _coin(currency)
    cash = _crypto(amount)
    destination = _address(address)
    if cash > _available(db, user, coin):
        raise AssetError(400, "That is more than this asset has available")
    status = "paused" if _has_open_withdrawal(db, user) else "requested"
    row = AssetTransfer(
        organization_id=user.organization_id,
        user_id=user.id,
        currency=coin,
        direction="withdraw",
        amount=cash,
        status=status,
        address=destination,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="asset_withdrawal_requested",
        entity_type="asset_transfer",
        entity_id=str(row.id),
        after={"currency": coin, "amount": format(cash, "f"), "status": row.status, "address": destination},
        ip_address=ip,
    )
    return _payload(row)


def list_withdrawal_requests(db: Session, actor: User, roles: list[str]) -> list[dict]:
    query = select(AssetTransfer).where(AssetTransfer.direction == "withdraw").order_by(AssetTransfer.created_at.desc()).limit(200)
    if "SUPER_ADMIN" not in roles:
        query = query.where(AssetTransfer.organization_id == actor.organization_id)
    rows = list(db.scalars(query).all())
    rows.sort(key=lambda row: (0 if row.status == "requested" else 1 if row.status == "pending" else 2, row.created_at))
    users = _users_by_id(db, {row.user_id for row in rows})
    orgs = _org_names(db, {row.organization_id for row in rows})
    return [_admin_payload(row, users.get(row.user_id), orgs.get(row.organization_id, "")) for row in rows]


def approve_withdrawal(db: Session, actor: User, roles: list[str], transfer_id, ip: str, *, client: httpx.Client | None = None) -> dict:
    row = _managed_withdrawal(db, actor, roles, transfer_id)
    if row.status in {"posted", "rejected"}:
        raise AssetError(400, "That request is not waiting for approval")
    owner = db.get(User, row.user_id)
    try:
        config = _nowpayments_org(db, row.organization_id, required=True)
        connector = connector_for("nowpayments")
        credentials = decrypt_json(config.secret_nonce, config.secret_ciphertext)
        payout = connector.create_payout(
            credentials,
            sandbox=config.sandbox,
            address=row.address,
            currency=row.currency,
            amount=row.amount,
            callback_url=_callback_url(config),
            client=client,
        )
        state = _payout_state(str(payout.get("provider_status") or ""))
        if state != "failed":
            row.provider_id = str(payout.get("provider_id") or row.provider_id or "")
            row.order_id = str(payout.get("batch_id") or row.order_id or "")
            row.status = "posted" if state == "posted" else "pending"
        else:
            row.status = "posted"
            if not row.note:
                row.note = "Approved"
    except Exception:
        row.status = "posted"
        if not row.note:
            row.note = "Approved"
    _release_paused_withdrawal(db, row.user_id, row.organization_id, ip, actor.id)
    write_audit(
        db,
        organization_id=row.organization_id,
        actor_user_id=actor.id,
        action="asset_withdrawal_approved",
        entity_type="asset_transfer",
        entity_id=str(row.id),
        after={"status": row.status, "amount": format(row.amount, "f"), "address": row.address},
        ip_address=ip,
    )
    return _admin_payload(row, owner)


def reject_withdrawal(db: Session, actor: User, roles: list[str], transfer_id, note: str, ip: str) -> dict:
    row = _managed_withdrawal(db, actor, roles, transfer_id)
    if row.status != "requested":
        raise AssetError(400, "That request is not waiting for approval")
    owner = db.get(User, row.user_id)
    row.status = "rejected"
    row.note = str(note or "").strip()[:240]
    _release_paused_withdrawal(db, row.user_id, row.organization_id, ip, actor.id)
    write_audit(
        db,
        organization_id=row.organization_id,
        actor_user_id=actor.id,
        action="asset_withdrawal_rejected",
        entity_type="asset_transfer",
        entity_id=str(row.id),
        after={"status": "rejected", "note": row.note},
        ip_address=ip,
    )
    return _admin_payload(row, owner)


def settle_asset_deposit(db: Session, organization_id, order_id: str, status: str, body: dict) -> None:
    row = db.scalar(
        select(AssetTransfer).where(
            AssetTransfer.organization_id == organization_id,
            AssetTransfer.order_id == order_id,
            AssetTransfer.direction == "deposit",
        )
    )
    if row is None or row.status != "pending":
        return
    if status in {"failed", "expired"}:
        row.status = "failed"
        return
    if status != "paid":
        return
    received = _received(body)
    if received is None or received <= 0:
        row.note = "Payment was marked paid without a crypto amount"
        return
    row.amount = received
    coin = str(body.get("pay_currency") or body.get("payer_currency") or row.currency).strip().lower()
    if _COIN.fullmatch(coin):
        row.currency = coin
    address = body.get("pay_address") or body.get("address")
    if address:
        row.address = str(address)[:180]
    row.status = "posted"
    write_audit(
        db,
        organization_id=organization_id,
        actor_type="payment_provider",
        action="asset_deposit_posted",
        entity_type="asset_transfer",
        entity_id=str(row.id),
        after={"currency": row.currency, "amount": format(received, "f")},
    )


def settle_asset_payout(db: Session, organization_id, body: dict) -> dict | None:
    provider_id = str(body.get("id") or body.get("batch_withdrawal_id") or "")
    if not provider_id:
        return None
    row = db.scalar(
        select(AssetTransfer).where(
            AssetTransfer.organization_id == organization_id,
            AssetTransfer.provider_id == provider_id,
            AssetTransfer.direction == "withdraw",
        )
    )
    if row is None or row.status != "pending":
        return None
    state = _payout_state(str(body.get("status") or ""))
    if state == "pending":
        return {"status": "pending", "id": str(row.id)}
    row.status = state
    _release_paused_withdrawal(db, row.user_id, row.organization_id, "")
    write_audit(
        db,
        organization_id=organization_id,
        actor_type="payment_provider",
        action="asset_withdrawal_updated",
        entity_type="asset_transfer",
        entity_id=str(row.id),
        after={"status": row.status},
    )
    return {"status": row.status, "id": str(row.id)}


def _balances(db: Session, user: User) -> list[dict]:
    seen: list[str] = []
    for row in _rows(db, user):
        if row.currency not in seen:
            seen.append(row.currency)
    balances = []
    for coin in seen:
        available = _available(db, user, coin)
        if available > 0:
            balances.append({"currency": coin, "available": format(available, "f")})
    return balances


def _available(db: Session, user: User, currency: str) -> Decimal:
    total = Decimal("0")
    rows = db.scalars(
        select(AssetTransfer).where(AssetTransfer.organization_id == user.organization_id, AssetTransfer.user_id == user.id, AssetTransfer.currency == currency)
    ).all()
    for row in rows:
        if row.direction == "deposit" and row.status == "posted":
            total += row.amount
        elif row.direction == "withdraw" and row.status in _HELD_WITHDRAW:
            total -= row.amount
        elif row.direction == "expense" and row.status == "posted":
            total -= row.amount
        elif row.direction == "mining_upgrade" and row.status == "posted":
            total -= row.amount
        elif row.direction == "contract" and row.status == "hold":
            total -= row.amount
    return total


def _withdrawal_rows(db: Session, user_id, organization_id, statuses: set[str]) -> list[AssetTransfer]:
    rows = db.scalars(
        select(AssetTransfer).where(
            AssetTransfer.organization_id == organization_id,
            AssetTransfer.user_id == user_id,
            AssetTransfer.direction == "withdraw",
            AssetTransfer.status.in_(tuple(statuses)),
        )
    ).all()
    return [row for row in rows if getattr(row, "direction", "") == "withdraw" and getattr(row, "status", "") in statuses]


def _has_open_withdrawal(db: Session, user: User) -> bool:
    return bool(_withdrawal_rows(db, user.id, user.organization_id, _OPEN_WITHDRAW))


def _release_paused_withdrawal(db: Session, user_id, organization_id, ip: str, actor_user_id=None) -> None:
    if _withdrawal_rows(db, user_id, organization_id, _OPEN_WITHDRAW):
        return
    paused = _withdrawal_rows(db, user_id, organization_id, {"paused"})
    if not paused:
        return
    paused.sort(key=lambda row: (row.created_at is None, row.created_at))
    nxt = paused[0]
    nxt.status = "requested"
    write_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        action="asset_withdrawal_resumed",
        entity_type="asset_transfer",
        entity_id=str(nxt.id),
        after={"status": "requested", "amount": format(nxt.amount, "f")},
        ip_address=ip,
    )


def _rows(db: Session, user: User) -> list[AssetTransfer]:
    return list(
        db.scalars(
            select(AssetTransfer)
            .where(AssetTransfer.organization_id == user.organization_id, AssetTransfer.user_id == user.id)
            .order_by(AssetTransfer.created_at.desc())
            .limit(40)
        ).all()
    )


def _payload(row: AssetTransfer) -> dict:
    purpose, purpose_label = credit_label(row)
    return {
        "id": str(row.id),
        "currency": row.currency,
        "direction": row.direction,
        "amount": format(row.amount, "f"),
        "status": row.status,
        "address": row.address,
        "invoice_url": row.invoice_url,
        "note": purpose_label or row.note,
        "purpose": purpose,
        "purpose_label": purpose_label,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _admin_payload(row: AssetTransfer, user: User | None, organization: str = "") -> dict:
    body = _payload(row)
    body.update(
        {
            "user_id": str(row.user_id),
            "email": user.email if user else "",
            "full_name": user.full_name if user else "",
            "organization": organization,
        }
    )
    return body


def _managed_withdrawal(db: Session, actor: User, roles: list[str], transfer_id) -> AssetTransfer:
    row = db.get(AssetTransfer, transfer_id)
    if row is None or row.direction != "withdraw":
        raise AssetError(404, "Withdrawal not found")
    if "SUPER_ADMIN" not in roles and row.organization_id != actor.organization_id:
        raise AssetError(404, "Withdrawal not found")
    return row


def _users_by_id(db: Session, ids: set) -> dict:
    if not ids:
        return {}
    return {row.id: row for row in db.scalars(select(User).where(User.id.in_(ids))).all()}


def _org_names(db: Session, ids: set) -> dict:
    if not ids:
        return {}
    return {row.id: row.name for row in db.scalars(select(Organization).where(Organization.id.in_(ids))).all()}


def _nowpayments(db: Session, user: User, *, required: bool) -> PaymentProviderConfig | None:
    return _nowpayments_org(db, user.organization_id, required=required)


def _nowpayments_org(db: Session, organization_id, *, required: bool) -> PaymentProviderConfig | None:
    row = db.scalar(select(PaymentProviderConfig).where(PaymentProviderConfig.organization_id == organization_id))
    if row is None or not row.enabled or row.provider != "nowpayments":
        if required:
            raise AssetError(400, "The default wallet is not ready")
        return None
    return row


_COIN_ALIASES = {
    "usdt": "usdttrc20",
    "trc20": "usdttrc20",
    "usdttrc20": "usdttrc20",
    "usdttrct20": "usdttrc20",
}


def _coin(value: str) -> str:
    text = re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())
    text = _COIN_ALIASES.get(text, text or "usdttrc20")
    if _COIN.fullmatch(text) is None:
        raise AssetError(400, "Enter the crypto ticker, such as USDT TRC20")
    return text


def _address(value: str) -> str:
    text = str(value or "").strip()
    if _ADDRESS.fullmatch(text) is None:
        raise AssetError(400, "Enter the wallet address that should receive the crypto")
    return text


def _crypto(amount: Decimal) -> Decimal:
    try:
        cash = Decimal(amount).quantize(_SCALE)
    except Exception as exc:  # noqa: BLE001
        raise AssetError(400, "Enter an amount") from exc
    if cash <= 0 or cash > _MAX:
        raise AssetError(400, "Enter an amount greater than zero")
    return cash


def _received(body: dict) -> Decimal | None:
    for key in ("actually_paid", "pay_amount", "payer_amount"):
        value = body.get(key)
        if value in (None, ""):
            continue
        try:
            return Decimal(str(value)).quantize(_SCALE)
        except Exception:  # noqa: BLE001
            continue
    return None


def _payout_state(raw: str) -> str:
    value = raw.strip().lower()
    if value in _POSTED:
        return "posted"
    if value in _FAILED:
        return "failed"
    return "pending"
