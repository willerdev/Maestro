from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domain.audit import write_audit
from app.models.chain_entities import ContractStake
from app.models.entities import AccountGrant, AssetTransfer, Organization, Session as AuthSession, User
from app.services.asset_service import AssetError, _available, _coin, _crypto, _payload
from app.services.auth_service import password_is_strong, role_codes_for


class AdminUserError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def list_managed_users(db: Session, actor: User, roles: list[str]) -> list[dict]:
    query = select(User).order_by(User.created_at.desc())
    if "SUPER_ADMIN" not in roles:
        query = query.where(User.organization_id == actor.organization_id)
    rows = list(db.scalars(query).all())
    names = _org_names(db, {row.organization_id for row in rows})
    pcoins = _pcoin_map(db, rows)
    wallets = _wallet_map(db, rows)
    contracts = _contract_map(db, rows)
    accounts = _account_map(db, rows)
    return [
        _card(
            db,
            row,
            names.get(row.organization_id, ""),
            wallet=wallets.get(row.id, Decimal("0")),
            pcoin=pcoins.get(row.id, "0"),
            yield_earned=contracts.get(row.id, (Decimal("0"), Decimal("0")))[0],
            held=contracts.get(row.id, (Decimal("0"), Decimal("0")))[1],
            accounts=accounts.get(row.id, 0),
        )
        for row in rows
    ]


def set_user_password(db: Session, actor: User, roles: list[str], user_id: UUID, password: str, ip: str) -> dict:
    target = _managed_user(db, actor, roles, user_id)
    if not password_is_strong(password):
        raise AdminUserError(400, "Password must be at least 12 characters and include a letter and a digit")
    target.password_hash = hash_password(password)
    _revoke_sessions(db, target.id)
    write_audit(
        db,
        organization_id=target.organization_id,
        actor_user_id=actor.id,
        action="admin_password_set",
        entity_type="user",
        entity_id=str(target.id),
        after={"email": target.email},
        ip_address=ip,
    )
    return _card(db, target)


def set_user_banned(db: Session, actor: User, roles: list[str], user_id: UUID, banned: bool, ip: str) -> dict:
    target = _managed_user(db, actor, roles, user_id)
    if target.id == actor.id:
        raise AdminUserError(400, "You cannot ban your own login")
    if banned and "SUPER_ADMIN" in role_codes_for(db, target.id) and "SUPER_ADMIN" not in roles:
        raise AdminUserError(403, "That account cannot be banned from this login")
    target.is_active = not banned
    if banned:
        _revoke_sessions(db, target.id)
    write_audit(
        db,
        organization_id=target.organization_id,
        actor_user_id=actor.id,
        action="admin_user_banned" if banned else "admin_user_unbanned",
        entity_type="user",
        entity_id=str(target.id),
        after={"email": target.email, "is_active": target.is_active},
        ip_address=ip,
    )
    return _card(db, target)


def allocate_wallet(db: Session, actor: User, roles: list[str], user_id: UUID, amount: Decimal, currency: str, ip: str) -> dict:
    target = _managed_user(db, actor, roles, user_id)
    coin = _coin(currency or "usdttrc20")
    try:
        cash = _crypto(amount)
    except AssetError as exc:
        raise AdminUserError(exc.status, exc.detail) from exc
    transfer = AssetTransfer(
        organization_id=target.organization_id,
        user_id=target.id,
        currency=coin,
        direction="deposit",
        amount=cash,
        status="posted",
        note="Wallet credit",
        order_id=f"AD{uuid4().hex[:16]}",
    )
    db.add(transfer)
    db.flush()
    write_audit(
        db,
        organization_id=target.organization_id,
        actor_user_id=actor.id,
        action="admin_wallet_allocated",
        entity_type="user",
        entity_id=str(target.id),
        after={"email": target.email, "amount": format(cash, "f"), "currency": coin},
        ip_address=ip,
    )
    return {"transfer": _payload(transfer), "user": _card(db, target)}


def _managed_user(db: Session, actor: User, roles: list[str], user_id: UUID) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise AdminUserError(404, "User not found")
    if "SUPER_ADMIN" not in roles and target.organization_id != actor.organization_id:
        raise AdminUserError(404, "User not found")
    return target


def _revoke_sessions(db: Session, user_id) -> None:
    now = datetime.now(timezone.utc)
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))).all():
        session.revoked_at = now


def _org_names(db: Session, ids: set) -> dict:
    if not ids:
        return {}
    rows = db.scalars(select(Organization).where(Organization.id.in_(ids))).all()
    return {row.id: row.name for row in rows}


def _card(
    db: Session,
    user: User,
    organization: str = "",
    *,
    wallet: Decimal | None = None,
    pcoin: str | None = None,
    yield_earned: Decimal | None = None,
    held: Decimal | None = None,
    accounts: int | None = None,
) -> dict:
    if not organization:
        org = db.get(Organization, user.organization_id)
        organization = org.name if org is not None else ""
    if wallet is None:
        wallet = _available(db, user, "usdttrc20") + _available(db, user, "usdt")
    if pcoin is None:
        pcoin = _pcoin_map(db, [user]).get(user.id, "0")
    if yield_earned is None or held is None:
        yield_earned, held = _contract_map(db, [user]).get(user.id, (Decimal("0"), Decimal("0")))
    if accounts is None:
        accounts = _account_map(db, [user]).get(user.id, 0)
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "roles": role_codes_for(db, user.id),
        "is_active": user.is_active,
        "organization": organization,
        "accounts": int(accounts),
        "wallet_usdt": format(wallet, "f"),
        "pcoin": pcoin,
        "contract_yield": format(yield_earned, "f"),
        "contract_held": format(held, "f"),
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


def _wallet_map(db: Session, users: list[User]) -> dict:
    totals = {row.id: Decimal("0") for row in users}
    if not users:
        return totals
    transfers = db.scalars(
        select(AssetTransfer).where(AssetTransfer.user_id.in_([row.id for row in users]), AssetTransfer.currency.in_(["usdttrc20", "usdt"]))
    ).all()
    for row in transfers:
        if row.user_id not in totals:
            continue
        if row.direction == "deposit" and row.status == "posted":
            totals[row.user_id] += row.amount
        elif row.direction == "withdraw" and row.status in {"posted", "pending", "requested"}:
            totals[row.user_id] -= row.amount
        elif row.direction == "expense" and row.status == "posted":
            totals[row.user_id] -= row.amount
        elif row.direction == "mining_upgrade" and row.status == "posted":
            totals[row.user_id] -= row.amount
        elif row.direction == "contract" and row.status == "hold":
            totals[row.user_id] -= row.amount
    return totals


def _contract_map(db: Session, users: list[User]) -> dict[UUID, tuple[Decimal, Decimal]]:
    totals = {row.id: (Decimal("0"), Decimal("0")) for row in users}
    if not users:
        return totals
    for stake in db.scalars(select(ContractStake).where(ContractStake.user_id.in_([row.id for row in users]))).all():
        earned, locked = totals.get(stake.user_id, (Decimal("0"), Decimal("0")))
        if stake.status == "hold":
            earned += stake.yield_earned or Decimal("0")
            locked += (stake.principal or Decimal("0")) + (stake.yield_earned or Decimal("0"))
        elif stake.status == "cancelled":
            locked += stake.principal or Decimal("0")
        totals[stake.user_id] = (earned, locked)
    return totals


def _account_map(db: Session, users: list[User]) -> dict:
    counts = {row.id: 0 for row in users}
    if not users:
        return counts
    for user_id, total in db.execute(select(AccountGrant.user_id, func.count()).where(AccountGrant.user_id.in_([row.id for row in users])).group_by(AccountGrant.user_id)):
        counts[user_id] = int(total)
    return counts


def _pcoin_map(db: Session, users: list[User]) -> dict:
    values = {row.id: "0" for row in users}
    if not users:
        return values
    try:
        from app.models.chain_entities import ChainWallet
        from app.services.chain_service import load_ledger
        from app.services.conversion_service import format_amount, pcoin_hold
    except Exception:
        return values
    by_org: dict = {}
    for row in users:
        by_org.setdefault(row.organization_id, []).append(row)
    for org_id, group in by_org.items():
        try:
            ledger = load_ledger(db, org_id)
            wallets = {
                wallet.user_id: wallet
                for wallet in db.scalars(select(ChainWallet).where(ChainWallet.organization_id == org_id, ChainWallet.user_id.in_([row.id for row in group]))).all()
            }
            for row in group:
                wallet = wallets.get(row.id)
                if wallet is None:
                    continue
                values[row.id] = format_amount(max(0, ledger.available(wallet.address) - pcoin_hold(db, org_id, row.id)))
        except Exception:
            continue
    return values
