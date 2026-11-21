from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chain.contract_yield import DEFAULT_BPS, LOCK_DAYS, MIN_DEPOSIT, clamp_rate_bps, daily_yield, is_unlocked, rate_label, unlock_at, working_day_profit
from app.domain.audit import write_audit
from app.models.chain_entities import ContractSettings, ContractStake, ContractYield
from app.models.entities import Account, AccountState, AssetTransfer, User
from app.services.account_service import get_visible_account, visible_account_query
from app.services.asset_service import _available, _payload

_USDT = ("usdttrc20", "usdt")
_SCALE = Decimal("0.00000001")
_PROFIT_BAND = re.compile(r"\[\[wd:(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)\]\]")


class ContractServiceError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def settings_for(db: Session, org_id) -> ContractSettings:
    row = db.get(ContractSettings, org_id)
    if row is None:
        row = ContractSettings(organization_id=org_id, daily_rate_bps=DEFAULT_BPS, min_deposit=MIN_DEPOSIT)
        db.add(row)
        db.flush()
    row.daily_rate_bps = clamp_rate_bps(row.daily_rate_bps)
    if row.min_deposit < MIN_DEPOSIT:
        row.min_deposit = MIN_DEPOSIT
    return row


def wallet_usdt(db: Session, user: User) -> Decimal:
    total = Decimal("0")
    for coin in _USDT:
        total += _available(db, user, coin)
    return total


def desk(db: Session, user: User, roles: list[str]) -> dict:
    accrue_user(db, user.id)
    rules = settings_for(db, user.organization_id)
    accounts = db.scalars(visible_account_query(db, user, roles).where(Account.connection_method == "blockchain")).all()
    stakes = db.scalars(
        select(ContractStake)
        .where(ContractStake.organization_id == user.organization_id, ContractStake.user_id == user.id)
        .order_by(ContractStake.created_at.desc())
    ).all()
    names = {row.id: row.display_name for row in accounts}
    return {
        "daily_rate": rate_label(rules.daily_rate_bps),
        "daily_rate_bps": rules.daily_rate_bps,
        "rate_range": "2.00% to 2.98%",
        "min_deposit": format(rules.min_deposit, "f"),
        "lock_days": LOCK_DAYS,
        "wallet_usdt": format(wallet_usdt(db, user), "f"),
        "wallet_currency": "usdttrc20",
        "accounts": [{"id": str(row.id), "display_name": row.display_name, "account_number": row.account_number} for row in accounts],
        "positions": [_stake_view(row, names.get(row.account_id, "Contract")) for row in stakes],
    }


def fund_contract(db: Session, user: User, roles: list[str], account_id: UUID, amount: Decimal, ip: str) -> dict:
    try:
        cash = Decimal(amount).quantize(_SCALE, rounding=ROUND_DOWN)
    except Exception as exc:
        raise ContractServiceError(400, "Enter an amount") from exc
    rules = settings_for(db, user.organization_id)
    if cash < rules.min_deposit:
        raise ContractServiceError(400, f"The minimum contract transfer is {format(rules.min_deposit, 'f')} USDT")
    available = wallet_usdt(db, user)
    if cash > available:
        raise ContractServiceError(400, "The default wallet does not have enough USDT. Convert mined PCoin or deposit first.")
    account = get_visible_account(db, user, roles, account_id)
    if account.connection_method != "blockchain":
        raise ContractServiceError(400, "Choose a blockchain contract account")
    coin = "usdttrc20" if _available(db, user, "usdttrc20") >= cash else "usdt"
    if _available(db, user, coin) < cash:
        raise ContractServiceError(400, "The default wallet does not have enough USDT")
    transfer = AssetTransfer(
        organization_id=user.organization_id,
        user_id=user.id,
        currency=coin,
        direction="contract",
        amount=cash,
        status="hold",
        note="Transferred to contract",
        address=account.account_number,
    )
    db.add(transfer)
    db.flush()
    today = datetime.now(timezone.utc).date()
    stake = ContractStake(
        organization_id=user.organization_id,
        user_id=user.id,
        account_id=account.id,
        transfer_id=transfer.id,
        principal=cash,
        yield_earned=Decimal("0"),
        status="hold",
        last_yield_on=today,
    )
    db.add(stake)
    db.flush()
    _mirror_contract_balance(db, stake)
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="contract_funded",
        entity_type="contract_stake",
        entity_id=str(stake.id),
        after={"amount": format(cash, "f"), "account_id": str(account.id), "status": "hold"},
        ip_address=ip,
    )
    from app.services.telegram_notice_service import notify_user

    notify_user(db, user.id, f"Contract update: {format(cash, 'f')} USDT moved onto {account.display_name}.")
    names = {account.id: account.display_name}
    return {"transfer": _payload(transfer), "position": _stake_view(stake, names[account.id]), "wallet_usdt": format(wallet_usdt(db, user), "f")}


def cancel_contract(db: Session, user: User, roles: list[str], stake_id: UUID, ip: str) -> dict:
    stake = _owned_stake(db, user, stake_id)
    if stake.status != "hold":
        raise ContractServiceError(400, "That contract transfer is not running")
    stake.yield_earned = Decimal("0")
    stake.status = "cancelled"
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="contract_cancelled",
        entity_type="contract_stake",
        entity_id=str(stake.id),
        after={"status": "cancelled", "principal": format(stake.principal, "f")},
        ip_address=ip,
    )
    return {"position": _stake_view(stake, _account_name(db, user, roles, stake.account_id)), "wallet_usdt": format(wallet_usdt(db, user), "f")}


def withdraw_contract(db: Session, user: User, roles: list[str], stake_id: UUID, ip: str) -> dict:
    stake = _owned_stake(db, user, stake_id)
    if stake.status not in {"hold", "cancelled"}:
        raise ContractServiceError(400, "That transfer is already off the contract")
    if not is_unlocked(stake.created_at):
        raise ContractServiceError(400, f"The transfer stays on the contract for {LOCK_DAYS} days")
    if stake.status == "hold":
        _accrue_stake(db, stake)
        returned = stake.principal + stake.yield_earned
        note = "Contract completed. Principal and yield returned to the default wallet."
    else:
        returned = stake.principal
        note = "Contract cancelled. Yield forfeited. Initial balance returned to the default wallet."
    transfer = db.get(AssetTransfer, stake.transfer_id) if stake.transfer_id else None
    coin = transfer.currency if transfer is not None else "usdttrc20"
    if transfer is not None:
        transfer.status = "released"
        transfer.note = note
    db.add(
        AssetTransfer(
            organization_id=user.organization_id,
            user_id=user.id,
            currency=coin,
            direction="deposit",
            amount=returned,
            status="posted",
            note=note,
            order_id=f"CT{stake.id.hex[:16]}",
        )
    )
    stake.status = "withdrawn"
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="contract_withdrawn",
        entity_type="contract_stake",
        entity_id=str(stake.id),
        after={"returned": format(returned, "f"), "status": "withdrawn"},
        ip_address=ip,
    )
    return {"returned": format(returned, "f"), "position": _stake_view(stake, _account_name(db, user, roles, stake.account_id)), "wallet_usdt": format(wallet_usdt(db, user), "f")}


def _owned_stake(db: Session, user: User, stake_id: UUID) -> ContractStake:
    stake = db.get(ContractStake, stake_id)
    if stake is None or stake.user_id != user.id or stake.organization_id != user.organization_id:
        raise ContractServiceError(404, "Contract transfer not found")
    return stake


def _account_name(db: Session, user: User, roles: list[str], account_id) -> str:
    try:
        return get_visible_account(db, user, roles, account_id).display_name
    except Exception:
        return "Contract"


def accrue_user(db: Session, user_id) -> int:
    rows = db.scalars(select(ContractStake).where(ContractStake.user_id == user_id, ContractStake.status == "hold")).all()
    credited = 0
    for stake in rows:
        credited += _accrue_stake(db, stake)
    return credited


def accrue_all(db: Session) -> int:
    rows = db.scalars(select(ContractStake).where(ContractStake.status == "hold")).all()
    credited = 0
    for stake in rows:
        credited += _accrue_stake(db, stake)
    return credited


def _profit_band(db: Session, stake: ContractStake) -> tuple[Decimal, Decimal] | None:
    transfer = db.get(AssetTransfer, stake.transfer_id) if stake.transfer_id else None
    if transfer is None:
        return None
    match = _PROFIT_BAND.search(transfer.note or "")
    if match is None:
        return None
    return Decimal(match.group(1)), Decimal(match.group(2))


def _mirror_contract_balance(db: Session, stake: ContractStake) -> None:
    if stake.status != "hold":
        return
    state = db.get(AccountState, stake.account_id)
    if state is None:
        return
    held = stake.principal + stake.yield_earned
    state.balance = held
    state.equity = held
    state.free_margin = held
    if state.peak_equity < held:
        state.peak_equity = held
    if state.day_start_equity <= 0:
        state.day_start_equity = stake.principal
    state.as_of = datetime.now(timezone.utc)


def _accrue_stake(db: Session, stake: ContractStake) -> int:
    rules = settings_for(db, stake.organization_id)
    band = _profit_band(db, stake)
    today = datetime.now(timezone.utc).date()
    credited = 0
    current = stake.last_yield_on
    while True:
        nxt = current + timedelta(days=1)
        if nxt > today:
            break
        if credited >= 30:
            break
        if band is None:
            held = stake.principal + stake.yield_earned
            amount = daily_yield(held, rules.daily_rate_bps)
            rate = rules.daily_rate_bps
        else:
            amount = working_day_profit(nxt, band[0], band[1])
            rate = 0
        if amount <= 0:
            stake.last_yield_on = nxt
            current = nxt
            continue
        existing = db.scalar(select(ContractYield).where(ContractYield.stake_id == stake.id, ContractYield.day == nxt))
        if existing is None:
            db.add(ContractYield(stake_id=stake.id, day=nxt, rate_bps=rate, amount=amount))
            stake.yield_earned += amount
            if state := db.get(AccountState, stake.account_id):
                state.day_start_equity = stake.principal + stake.yield_earned - amount
        stake.last_yield_on = nxt
        current = nxt
        credited += 1
    _mirror_contract_balance(db, stake)
    if credited:
        from app.services.telegram_notice_service import notify_user

        notify_user(db, stake.user_id, f"Contract update: {format(stake.yield_earned, 'f')} USDT is now earned on the contract.")
    return credited


def _stake_view(row: ContractStake, name: str) -> dict:
    held = row.principal if row.status == "cancelled" else row.principal + row.yield_earned
    unlocked = is_unlocked(row.created_at)
    if row.status == "hold":
        label = "transferred to contract"
    elif row.status == "cancelled":
        label = "cancelled, yield forfeited"
    elif row.status == "withdrawn":
        label = "returned to wallet"
    else:
        label = row.status
    return {
        "id": str(row.id),
        "account_id": str(row.account_id),
        "account": name,
        "principal": format(row.principal, "f"),
        "yield_earned": format(Decimal("0") if row.status == "cancelled" else row.yield_earned, "f"),
        "held": format(held, "f"),
        "status": label,
        "locked": not unlocked and row.status in {"hold", "cancelled"},
        "can_cancel": row.status == "hold",
        "can_withdraw": unlocked and row.status in {"hold", "cancelled"},
        "unlock_at": unlock_at(row.created_at).isoformat(),
        "lock_days": LOCK_DAYS,
        "last_yield_on": row.last_yield_on.isoformat() if row.last_yield_on else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
