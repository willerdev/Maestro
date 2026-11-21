from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from tradeguard_risk.drawdown import current_drawdown_pct

from app.domain.audit import write_audit
from app.models.entities import Account, AccountState, AssetTransfer, Role, User, UserRole
from app.services.account_service import AccountError, load_credentials, save_credentials
from app.services.asset_service import _available

FEE = Decimal("100")
COIN = "usdttrc20"
BREACH_DRAWDOWN = Decimal("10")


def take_challenge_fee(db: Session, user: User, account: Account, credentials: dict, ip: str) -> None:
    if not credentials.get("accepted_terms"):
        raise AccountError(400, "Agree to the $100 challenge fee before saving.")
    if _available(db, user, COIN) < FEE:
        raise AccountError(400, "Deposit $100 USDT TRC20 to take this challenge.")
    reference = f"PP{account.id.hex[:16]}{uuid4().hex[:4]}"
    db.add(
        AssetTransfer(
            organization_id=user.organization_id,
            user_id=user.id,
            currency=COIN,
            direction="expense",
            amount=FEE,
            status="posted",
            note="Pass Props challenge fee",
            order_id=reference,
        )
    )
    receiver = _receiver(db, user)
    if receiver is not None:
        db.add(
            AssetTransfer(
                organization_id=receiver.organization_id,
                user_id=receiver.id,
                currency=COIN,
                direction="deposit",
                amount=FEE,
                status="posted",
                note=f"Pass Props fee from {user.email}",
                order_id=reference,
            )
        )
    credentials["challenge_fee"] = "100"
    credentials["challenge_fee_order"] = reference
    credentials["challenge_fee_status"] = "charged"
    write_audit(
        db,
        organization_id=account.organization_id,
        actor_user_id=user.id,
        action="passprop_fee_charged",
        entity_type="account",
        entity_id=str(account.id),
        after={"amount": "100", "currency": COIN, "order": reference},
        ip_address=ip,
    )
    db.flush()


def maybe_refund_breach(db: Session, actor: User, account: Account, ip: str, *, force: bool = False) -> dict:
    if account.connection_method != "passprop":
        raise AccountError(400, "That is not a Pass Props account")
    creds = load_credentials(db, account.id)
    status = str(creds.get("challenge_fee_status") or "")
    public = challenge_public(creds)
    if status == "refunded":
        return public
    if status != "charged":
        return public
    if not force and not _is_breached(db, account, creds):
        return public
    _refund(db, actor, account, creds, ip)
    save_credentials(db, account.id, creds)
    db.flush()
    return challenge_public(creds)


def challenge_public(creds: dict) -> dict:
    status = str(creds.get("challenge_fee_status") or "")
    return {
        "fee": "100",
        "fee_status": status or "unpaid",
        "refund_on_breach": True,
    }


def _is_breached(db: Session, account: Account, creds: dict) -> bool:
    state = db.get(AccountState, account.id)
    if state is None or state.equity is None:
        return False
    if state.equity <= 0:
        return True
    dd = current_drawdown_pct(state.peak_equity or Decimal("0"), state.equity)
    if dd >= BREACH_DRAWDOWN:
        return True
    try:
        size = Decimal(str(creds.get("account_size") or "0").replace(",", "") or "0")
    except Exception:  # noqa: BLE001
        size = Decimal("0")
    if size > 0 and (state.equity - size) / size * Decimal("100") <= -BREACH_DRAWDOWN:
        return True
    return False


def _refund(db: Session, actor: User, account: Account, creds: dict, ip: str) -> None:
    order = str(creds.get("challenge_fee_order") or "")
    expense = None
    if order:
        expense = db.scalar(
            select(AssetTransfer).where(AssetTransfer.order_id == order, AssetTransfer.direction == "expense")
        )
    payer = db.get(User, expense.user_id) if expense is not None else actor
    if payer is None:
        payer = actor
    refund_order = f"PR{account.id.hex[:16]}{uuid4().hex[:4]}"
    db.add(
        AssetTransfer(
            organization_id=payer.organization_id,
            user_id=payer.id,
            currency=COIN,
            direction="deposit",
            amount=FEE,
            status="posted",
            note="Pass Props breach refund",
            order_id=refund_order,
        )
    )
    receiver = _receiver(db, payer)
    if receiver is not None and _available(db, receiver, COIN) >= FEE:
        db.add(
            AssetTransfer(
                organization_id=receiver.organization_id,
                user_id=receiver.id,
                currency=COIN,
                direction="expense",
                amount=FEE,
                status="posted",
                note=f"Pass Props refund to {payer.email}",
                order_id=refund_order,
            )
        )
    creds["challenge_fee_status"] = "refunded"
    creds["challenge_refund_order"] = refund_order
    write_audit(
        db,
        organization_id=account.organization_id,
        actor_user_id=actor.id,
        action="passprop_fee_refunded",
        entity_type="account",
        entity_id=str(account.id),
        after={"amount": "100", "currency": COIN, "order": refund_order},
        ip_address=ip,
    )


def _receiver(db: Session, payer: User) -> User | None:
    return db.scalar(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.organization_id == payer.organization_id,
            User.is_active.is_(True),
            Role.code == "SUPER_ADMIN",
            User.id != payer.id,
        )
        .order_by(User.created_at.asc())
    )
