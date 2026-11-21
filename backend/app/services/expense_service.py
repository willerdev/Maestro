from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.audit import write_audit
from app.models.entities import AssetTransfer, OperatingCycle, Role, User, UserRole
from app.services.asset_service import _available, _payload
from app.services.auth_service import role_codes_for
from app.services.license_service import is_licensed

FEE = Decimal("500")
MIN_CHARGE = Decimal("2")
MAX_CHARGE = Decimal("68")
CYCLE_DAYS = 5
HOUR = timedelta(hours=1)
COIN = "usdttrc20"
_SCALE = Decimal("0.01")
_DESK = {"ADMIN", "RISK_MANAGER", "TRADER", "VIEWER"}


def next_expense_amount(remaining: Decimal, hours_left: int) -> Decimal:
    leftover = Decimal(remaining).quantize(_SCALE, rounding=ROUND_DOWN)
    if leftover <= 0:
        return Decimal("0")
    slots = max(1, int(hours_left))
    if leftover <= MIN_CHARGE:
        return leftover
    if slots == 1:
        return leftover if leftover <= MAX_CHARGE else MAX_CHARGE
    min_leave = MIN_CHARGE * (slots - 1)
    max_leave = MAX_CHARGE * (slots - 1)
    low = max(MIN_CHARGE, leftover - max_leave)
    high = min(MAX_CHARGE, leftover - min_leave)
    if high < low:
        return leftover if leftover <= MAX_CHARGE else MAX_CHARGE
    low_cents = int(low * 100)
    high_cents = int(high * 100)
    if high_cents < low_cents:
        high_cents = low_cents
    cash = (Decimal(random.randint(low_cents, high_cents)) / Decimal("100")).quantize(_SCALE)
    if cash > leftover:
        cash = leftover
    if cash < MIN_CHARGE and leftover >= MIN_CHARGE:
        cash = MIN_CHARGE
    return cash


def hours_left(now: datetime, ends_at: datetime) -> int:
    seconds = (ends_at - now).total_seconds()
    if seconds <= 0:
        return 1
    return max(1, int(math.ceil(seconds / 3600)))


def is_chargeable(roles: list[str]) -> bool:
    if "SUPER_ADMIN" in roles:
        return False
    return bool(_DESK.intersection(roles))


def deposit_ready(db: Session, user: User, roles: list[str]) -> bool:
    return bool(_status(db, user, roles).get("funded"))


def operating_status(db: Session, user: User, roles: list[str], device_id: str = "") -> dict:
    tick_user(db, user, roles)
    return _status(db, user, roles, device_id)


def tick_operating_fees(db: Session) -> None:
    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    for user in users:
        tick_user(db, user, role_codes_for(db, user.id))


def tick_user(db: Session, user: User, roles: list[str]) -> None:
    if not is_chargeable(roles) or not user.is_active:
        return
    receiver = _receiver(db, user)
    if receiver is None or receiver.id == user.id:
        return
    now = datetime.now(timezone.utc)
    cycle = _active_cycle(db, user.id)
    available = _available(db, user, COIN)
    if cycle is None:
        if available >= FEE:
            cycle = OperatingCycle(
                organization_id=user.organization_id,
                user_id=user.id,
                started_at=now,
                ends_at=now + timedelta(days=CYCLE_DAYS),
                target=FEE,
                collected=Decimal("0"),
                status="active",
            )
            db.add(cycle)
            db.flush()
            _charge(db, user, receiver, cycle, now)
        return
    remaining = cycle.target - cycle.collected
    if remaining <= 0:
        cycle.status = "completed"
        return
    if cycle.last_charged_at is not None and now - cycle.last_charged_at < HOUR:
        return
    _charge(db, user, receiver, cycle, now)


def _charge(db: Session, user: User, receiver: User, cycle: OperatingCycle, now: datetime) -> None:
    remaining = cycle.target - cycle.collected
    if remaining <= 0:
        cycle.status = "completed"
        return
    cash = next_expense_amount(remaining, hours_left(now, cycle.ends_at))
    if cash <= 0:
        return
    available = _available(db, user, COIN)
    if available < cash:
        return
    reference = f"EX{cycle.id.hex[:16]}{uuid4().hex[:6]}"
    db.add(
        AssetTransfer(
            organization_id=user.organization_id,
            user_id=user.id,
            currency=COIN,
            direction="expense",
            amount=cash,
            status="posted",
            note="Operating expense",
            order_id=reference,
        )
    )
    db.add(
        AssetTransfer(
            organization_id=receiver.organization_id,
            user_id=receiver.id,
            currency=COIN,
            direction="deposit",
            amount=cash,
            status="posted",
            note=f"Operating expense from {user.email}",
            order_id=reference,
        )
    )
    cycle.collected = (cycle.collected + cash).quantize(_SCALE)
    cycle.last_charged_at = now
    if cycle.collected >= cycle.target:
        cycle.status = "completed"
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_type="system",
        action="operating_expense",
        entity_type="operating_cycle",
        entity_id=str(cycle.id),
        after={"amount": format(cash, "f"), "collected": format(cycle.collected, "f"), "user": user.email},
    )
    db.flush()


def _status(db: Session, user: User, roles: list[str], device_id: str = "") -> dict:
    available = _available(db, user, COIN)
    licensed = is_licensed(db, user, roles, device_id)
    if not is_chargeable(roles):
        return {
            "required": False,
            "allowed": True,
            "licensed": True,
            "funded": True,
            "mining_allowed": True,
            "minimum": format(FEE, "f"),
            "available": format(available, "f"),
            "cycle": None,
            "reason": "",
            "expenses": [],
        }
    cycle = _active_cycle(db, user.id)
    expenses = [
        _payload(row)
        for row in db.scalars(
            select(AssetTransfer)
            .where(AssetTransfer.user_id == user.id, AssetTransfer.direction == "expense")
            .order_by(AssetTransfer.created_at.desc())
            .limit(12)
        ).all()
    ]
    remaining = (cycle.target - cycle.collected) if cycle else FEE
    funded = cycle is not None or available >= FEE
    if cycle is not None and remaining > 0 and available < MIN_CHARGE:
        funded = False
    reasons = []
    if not licensed:
        reasons.append("Enter a license key to activate this computer.")
    if not funded:
        reasons.append("Deposit a minimum of $500 to operate.")
    return {
        "required": True,
        "allowed": licensed and funded,
        "licensed": licensed,
        "funded": funded,
        "mining_allowed": licensed,
        "minimum": format(FEE, "f"),
        "available": format(available, "f"),
        "cycle": None
        if cycle is None
        else {
            "started_at": cycle.started_at.isoformat() if cycle.started_at else "",
            "ends_at": cycle.ends_at.isoformat() if cycle.ends_at else "",
            "target": format(cycle.target, "f"),
            "collected": format(cycle.collected, "f"),
            "remaining": format(max(Decimal("0"), remaining), "f"),
            "hours_left": hours_left(datetime.now(timezone.utc), cycle.ends_at),
            "last_charged_at": cycle.last_charged_at.isoformat() if cycle.last_charged_at else "",
        },
        "reason": " ".join(reasons),
        "expenses": expenses,
    }


def _active_cycle(db: Session, user_id) -> OperatingCycle | None:
    return db.scalar(
        select(OperatingCycle)
        .where(OperatingCycle.user_id == user_id, OperatingCycle.status == "active")
        .order_by(OperatingCycle.started_at.desc())
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
