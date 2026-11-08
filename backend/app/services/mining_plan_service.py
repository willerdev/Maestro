"""Optional premium mining on top of existing Project Coin proof-of-work.

Free SHA-256 mining is unchanged. A paid plan only adds extra PCoin while a
session is actually running, using elapsed time and Decimal math. Upgrades
activate only after a verified wallet debit or payment IPN.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.chain.money import UNIT, format_amount, parse_amount
from app.domain.audit import write_audit
from app.models.chain_entities import (
    ChainHit,
    ChainWallet,
    MiningPlan,
    MiningRewardLedger,
    MiningSettings,
    MiningUpgradePayment,
    UserMiningUpgrade,
)
from app.models.entities import AssetTransfer, Role, User, UserRole

logger = logging.getLogger(__name__)

DAY = Decimal("86400")
_SCALE = Decimal("0.00000001")
_DEFAULT_PLANS = (
    ("free", "Free Miner", "0", "1", 0, 0, "Proof-of-work mining with no purchase. Existing balances stay intact."),
    ("starter", "Starter Miner", "5", "1.25", 30, 1, "Adds 0.25x extra PCoin while your miner is running."),
    ("silver", "Silver Miner", "15", "1.5", 30, 2, "Adds 0.5x extra PCoin while your miner is running."),
    ("gold", "Gold Miner", "30", "2", 30, 3, "Adds 1x extra PCoin while your miner is running."),
    ("platinum", "Platinum Miner", "50", "2.5", 30, 4, "Adds 1.5x extra PCoin while your miner is running."),
    ("diamond", "Diamond Miner", "100", "3", 30, 5, "Adds 2x extra PCoin while your miner is running."),
)


class MiningPlanError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def extra_atomic(base_daily: Decimal, multiplier: Decimal, seconds: float, cap_remaining: int | None = None) -> int:
    """Premium extra for elapsed seconds. Free (1x) always returns 0."""
    extra_rate = (base_daily * (multiplier - Decimal("1"))).quantize(_SCALE, rounding=ROUND_DOWN)
    if extra_rate <= 0 or seconds <= 0:
        return 0
    coins = (extra_rate * Decimal(str(seconds)) / DAY).quantize(_SCALE, rounding=ROUND_DOWN)
    atomic = int(coins * UNIT)
    if cap_remaining is not None:
        atomic = min(atomic, max(0, cap_remaining))
    return max(0, atomic)


def _dec(value: str | Decimal, field: str = "amount") -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise MiningPlanError(400, f"Enter a valid {field}") from exc
    if number < 0:
        raise MiningPlanError(400, f"Enter a valid {field}")
    return number


def _multiplier(value: str | Decimal) -> Decimal:
    number = _dec(value, "multiplier")
    if number < 1:
        raise MiningPlanError(400, "Multiplier must be at least 1")
    return number.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settings(db: Session, org_id) -> MiningSettings:
    row = db.get(MiningSettings, org_id)
    if row is None:
        row = MiningSettings(organization_id=org_id)
        db.add(row)
        db.flush()
    return row


def ensure_plans(db: Session, org_id) -> None:
    _settings(db, org_id)
    existing = db.scalars(select(MiningPlan).where(MiningPlan.organization_id == org_id)).all()
    if existing:
        return
    duration = _settings(db, org_id).default_duration_days
    for code, name, price, multiplier, days, order, benefits in _DEFAULT_PLANS:
        db.add(
            MiningPlan(
                organization_id=org_id,
                code=code,
                name=name,
                price=Decimal(price),
                multiplier=multiplier,
                duration_days=0 if code == "free" else duration or days,
                sort_order=order,
                benefits=benefits,
            )
        )
    db.flush()


def mining_paused(db: Session, org_id) -> bool:
    row = db.get(MiningSettings, org_id)
    return bool(row and row.paused)


def assert_mining_allowed(db: Session, org_id) -> None:
    if mining_paused(db, org_id):
        raise MiningPlanError(403, "Mining is paused")


def free_plan(db: Session, org_id) -> MiningPlan:
    ensure_plans(db, org_id)
    row = db.scalar(select(MiningPlan).where(MiningPlan.organization_id == org_id, MiningPlan.code == "free"))
    if row is None:
        raise MiningPlanError(500, "The free mining plan is missing")
    return row


def active_upgrade(db: Session, org_id, user_id) -> UserMiningUpgrade | None:
    now = _now()
    row = db.scalar(
        select(UserMiningUpgrade)
        .where(UserMiningUpgrade.organization_id == org_id, UserMiningUpgrade.user_id == user_id, UserMiningUpgrade.status == "active")
        .order_by(UserMiningUpgrade.started_at.desc())
    )
    if row is None:
        return None
    if row.ends_at is not None and row.ends_at <= now:
        row.status = "expired"
        db.flush()
        return None
    return row


def active_multiplier(db: Session, org_id, user_id) -> Decimal:
    row = active_upgrade(db, org_id, user_id)
    if row is None:
        return Decimal("1")
    try:
        return _multiplier(row.multiplier)
    except MiningPlanError:
        return Decimal("1")


def bonus_available(db: Session, org_id, user_id) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(MiningRewardLedger.amount_atomic), 0)).where(
            MiningRewardLedger.organization_id == org_id,
            MiningRewardLedger.user_id == user_id,
        )
    )
    return max(0, int(total or 0))


def _credits_since(db: Session, org_id, user_id, start: datetime | None = None) -> int:
    query = select(func.coalesce(func.sum(MiningRewardLedger.amount_atomic), 0)).where(
        MiningRewardLedger.organization_id == org_id,
        MiningRewardLedger.user_id == user_id,
        MiningRewardLedger.amount_atomic > 0,
    )
    if start is not None:
        query = query.where(MiningRewardLedger.created_at >= start)
    return int(db.scalar(query) or 0)


def _session_running(org_id, user_id) -> bool:
    from app.services.chain_service import _CONTROLS, _CONTROL_LOCK, _control_key

    with _CONTROL_LOCK:
        control = _CONTROLS.get(_control_key(org_id, user_id))
    return control is not None and control.status == "running"


def arm_accrual(db: Session, org_id, user_id) -> None:
    row = active_upgrade(db, org_id, user_id)
    if row is not None:
        row.last_accrued_at = _now()
        db.flush()


def flush_accrual(db: Session, org_id, user_id) -> None:
    accrue_user(db, org_id, user_id)
    row = active_upgrade(db, org_id, user_id)
    if row is not None:
        row.last_accrued_at = None
        db.flush()


def accrue_user(db: Session, org_id, user_id) -> int:
    if mining_paused(db, org_id) or not _session_running(org_id, user_id):
        return 0
    row = (
        db.scalars(
            select(UserMiningUpgrade)
            .where(UserMiningUpgrade.organization_id == org_id, UserMiningUpgrade.user_id == user_id, UserMiningUpgrade.status == "active")
            .order_by(UserMiningUpgrade.started_at.desc())
            .with_for_update()
        )
        .first()
    )
    if row is None:
        return 0
    now = _now()
    if row.ends_at is not None and row.ends_at <= now:
        row.status = "expired"
        row.last_accrued_at = None
        return 0
    multiplier = _multiplier(row.multiplier)
    if multiplier <= 1:
        row.last_accrued_at = now
        return 0
    if row.last_accrued_at is None:
        row.last_accrued_at = now
        return 0
    seconds = (now - row.last_accrued_at).total_seconds()
    if seconds < 1:
        return 0
    settings = _settings(db, org_id)
    base = _dec(settings.base_daily_pcoin, "base daily PCoin")
    plan = db.get(MiningPlan, row.plan_id)
    cap = None
    if plan is not None and plan.daily_limit not in {"", "0"}:
        try:
            limit = parse_amount(plan.daily_limit)
        except ValueError:
            limit = 0
        if limit > 0:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            cap = max(0, limit - _credits_since(db, org_id, user_id, start))
            if cap == 0:
                row.last_accrued_at = now
                return 0
    atomic = extra_atomic(base, multiplier, seconds, cap)
    started = int(row.last_accrued_at.timestamp())
    row.last_accrued_at = now
    if atomic <= 0:
        return 0
    reference = f"AC{row.id.hex[:16]}{started}{int(now.timestamp())}"[:80]
    duplicate = db.scalar(select(MiningRewardLedger.id).where(MiningRewardLedger.organization_id == org_id, MiningRewardLedger.reference == reference))
    if duplicate is not None:
        return 0
    try:
        with db.begin_nested():
            db.add(
                MiningRewardLedger(
                    organization_id=org_id,
                    user_id=user_id,
                    upgrade_id=row.id,
                    plan_id=row.plan_id,
                    kind="premium_accrual",
                    amount_atomic=atomic,
                    multiplier=str(multiplier),
                    reference=reference,
                    note="Premium mining extra for elapsed runtime",
                )
            )
            db.flush()
    except IntegrityError:
        return 0
    write_audit(
        db,
        organization_id=org_id,
        actor_type="system",
        action="mining_premium_accrual",
        entity_type="mining_reward_ledger",
        entity_id=reference,
        after={"amount": format_amount(atomic), "multiplier": str(multiplier), "seconds": int(seconds)},
    )
    return atomic


def tick_all_accruals(db: Session) -> None:
    rows = db.scalars(select(UserMiningUpgrade).where(UserMiningUpgrade.status == "active")).all()
    seen: set[tuple] = set()
    for row in rows:
        key = (row.organization_id, row.user_id)
        if key in seen:
            continue
        seen.add(key)
        try:
            accrue_user(db, row.organization_id, row.user_id)
        except Exception:
            logger.exception("mining_accrual_failed user=%s", row.user_id)


def _plan_payload(db: Session, plan: MiningPlan, org_id, user_id) -> dict:
    settings = _settings(db, org_id)
    multiplier = _multiplier(plan.multiplier)
    base = _dec(settings.base_daily_pcoin, "base daily PCoin")
    current = active_upgrade(db, org_id, user_id)
    speed = (base * multiplier).quantize(_SCALE, rounding=ROUND_DOWN)
    extra = (base * (multiplier - Decimal("1"))).quantize(_SCALE, rounding=ROUND_DOWN)
    return {
        "id": str(plan.id),
        "code": plan.code,
        "name": plan.name,
        "price": format(plan.price, "f"),
        "currency": "USDT",
        "multiplier": str(multiplier),
        "duration_days": plan.duration_days,
        "daily_limit": plan.daily_limit,
        "benefits": plan.benefits,
        "enabled": plan.enabled,
        "sort_order": plan.sort_order,
        "base_daily": format(base, "f"),
        "speed_daily": format(speed, "f"),
        "extra_daily": format(extra, "f"),
        "active": bool(current and current.plan_id == plan.id),
        "free": plan.code == "free" or plan.price <= 0,
    }


def list_plans(db: Session, org_id, user_id, *, include_disabled: bool = False) -> list[dict]:
    ensure_plans(db, org_id)
    accrue_user(db, org_id, user_id)
    query = select(MiningPlan).where(MiningPlan.organization_id == org_id).order_by(MiningPlan.sort_order, MiningPlan.price)
    if not include_disabled:
        query = query.where(MiningPlan.enabled.is_(True))
    return [_plan_payload(db, row, org_id, user_id) for row in db.scalars(query).all()]


def _wallet_coin(db: Session, user: User, cash: Decimal) -> str:
    from app.services.asset_service import _available

    if _available(db, user, "usdttrc20") >= cash:
        return "usdttrc20"
    if _available(db, user, "usdt") >= cash:
        return "usdt"
    raise MiningPlanError(400, "Deposit USDT TRC20 first. The upgrade is not activated until the wallet debit succeeds.")


def _debit_wallet(db: Session, user: User, cash: Decimal, reference: str, note: str) -> None:
    coin = _wallet_coin(db, user, cash)
    db.add(
        AssetTransfer(
            organization_id=user.organization_id,
            user_id=user.id,
            currency=coin,
            direction="mining_upgrade",
            amount=cash,
            status="posted",
            note=note,
            order_id=reference,
        )
    )
    receiver = db.scalar(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.organization_id == user.organization_id,
            User.is_active.is_(True),
            Role.code == "SUPER_ADMIN",
            User.id != user.id,
        )
        .order_by(User.created_at.asc())
    )
    if receiver is not None:
        db.add(
            AssetTransfer(
                organization_id=receiver.organization_id,
                user_id=receiver.id,
                currency=coin,
                direction="deposit",
                amount=cash,
                status="posted",
                note=f"Mining upgrade from {user.email}",
                order_id=reference,
            )
        )


def _activate(db: Session, user: User, plan: MiningPlan, payment: MiningUpgradePayment) -> UserMiningUpgrade:
    if payment.upgrade_id:
        existing = db.get(UserMiningUpgrade, payment.upgrade_id)
        if existing is not None:
            return existing
    current = active_upgrade(db, user.organization_id, user.id)
    if current is not None:
        accrue_user(db, user.organization_id, user.id)
        current.status = "replaced"
        current.last_accrued_at = None
    now = _now()
    ends = now + timedelta(days=plan.duration_days) if plan.duration_days > 0 else None
    upgrade = UserMiningUpgrade(
        organization_id=user.organization_id,
        user_id=user.id,
        plan_id=plan.id,
        status="active",
        multiplier=plan.multiplier,
        started_at=now,
        ends_at=ends,
        last_accrued_at=now if _session_running(user.organization_id, user.id) else None,
    )
    db.add(upgrade)
    db.flush()
    payment.upgrade_id = upgrade.id
    payment.status = "paid"
    payment.paid_at = now
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        actor_type="system",
        action="mining_upgrade_activated",
        entity_type="user_mining_upgrade",
        entity_id=str(upgrade.id),
        after={"plan": plan.code, "multiplier": plan.multiplier, "reference": payment.reference, "ends_at": ends.isoformat() if ends else ""},
    )
    return upgrade


def purchase_upgrade(db: Session, user: User, plan_id: str, method: str, ip: str) -> dict:
    ensure_plans(db, user.organization_id)
    try:
        plan = db.get(MiningPlan, UUID(str(plan_id)))
    except (TypeError, ValueError) as exc:
        raise MiningPlanError(400, "Choose a mining plan") from exc
    if plan is None or plan.organization_id != user.organization_id or not plan.enabled:
        raise MiningPlanError(404, "That mining plan is not available")
    if plan.code == "free" or plan.price <= 0:
        raise MiningPlanError(400, "The free miner does not require a purchase")
    settings = _settings(db, user.organization_id)
    if _multiplier(plan.multiplier) > _multiplier(settings.max_multiplier):
        raise MiningPlanError(400, "That plan is above the maximum upgrade level")
    current = active_upgrade(db, user.organization_id, user.id)
    if current is not None and current.plan_id == plan.id:
        raise MiningPlanError(409, "That plan is already active")
    pay_method = str(method or "wallet").strip().lower()
    if pay_method not in {"wallet", "invoice"}:
        raise MiningPlanError(400, "Pay from the wallet or open an invoice")
    cash = plan.price.quantize(_SCALE, rounding=ROUND_DOWN)
    if pay_method == "wallet":
        reference = f"MU{uuid4().hex[:22]}"
        payment = MiningUpgradePayment(
            organization_id=user.organization_id,
            user_id=user.id,
            plan_id=plan.id,
            reference=reference,
            amount=cash,
            currency="usdttrc20",
            method="wallet",
            status="pending",
            note=f"{plan.name} mining upgrade",
        )
        db.add(payment)
        db.flush()
        try:
            _debit_wallet(db, user, cash, reference, f"{plan.name} mining upgrade")
        except MiningPlanError:
            payment.status = "failed"
            payment.note = "Wallet debit failed"
            raise
        upgrade = _activate(db, user, plan, payment)
        db.flush()
        return {**_payment_payload(payment, plan), "upgrade": _upgrade_payload(upgrade, plan), "activated": True}
    from app.services.payment_service import PaymentError, create_payment

    try:
        created = create_payment(
            db,
            user,
            {
                "price_amount": cash,
                "price_currency": "USD",
                "pay_currency": "usdttrc20",
                "purpose": "mining_upgrade",
                "description": f"{plan.name} mining upgrade",
            },
            ip,
        )
    except PaymentError as exc:
        raise MiningPlanError(exc.status, exc.detail) from exc
    payment = MiningUpgradePayment(
        organization_id=user.organization_id,
        user_id=user.id,
        plan_id=plan.id,
        reference=str(created.get("order_id") or ""),
        amount=cash,
        currency="usdttrc20",
        method="invoice",
        status="pending",
        invoice_url=str(created.get("invoice_url") or ""),
        note=f"{plan.name} mining upgrade",
    )
    db.add(payment)
    db.flush()
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="mining_upgrade_invoice",
        entity_type="mining_upgrade_payment",
        entity_id=str(payment.id),
        after={"plan": plan.code, "reference": payment.reference, "amount": format(cash, "f")},
        ip_address=ip,
    )
    return {**_payment_payload(payment, plan), "upgrade": None, "activated": False, "invoice": created}


def settle_mining_upgrade(db: Session, organization_id, order_id: str, status: str, body: dict) -> None:
    if not order_id:
        return
    payment = db.scalar(
        select(MiningUpgradePayment).where(MiningUpgradePayment.organization_id == organization_id, MiningUpgradePayment.reference == order_id)
    )
    if payment is None:
        return
    if payment.status == "paid" and payment.upgrade_id:
        return
    mapped = str(status or "").strip().lower()
    if mapped in {"failed", "expired", "underpaid"}:
        payment.status = "failed"
        payment.note = f"Payment {mapped}"
        return
    if mapped != "paid":
        payment.status = "pending"
        return
    plan = db.get(MiningPlan, payment.plan_id)
    if plan is None:
        payment.status = "failed"
        payment.note = "Plan missing"
        return
    received = body.get("price_amount") or body.get("actually_paid") or body.get("pay_amount") or payment.amount
    try:
        cash = Decimal(str(received)).quantize(_SCALE)
    except (InvalidOperation, TypeError):
        cash = payment.amount
    if cash + Decimal("0.01") < payment.amount:
        payment.status = "failed"
        payment.note = "Paid amount was below the plan price"
        return
    user = db.get(User, payment.user_id)
    if user is None:
        payment.status = "failed"
        return
    _activate(db, user, plan, payment)


def list_upgrade_payments(db: Session, org_id, user_id) -> list[dict]:
    rows = db.scalars(
        select(MiningUpgradePayment)
        .where(MiningUpgradePayment.organization_id == org_id, MiningUpgradePayment.user_id == user_id)
        .order_by(MiningUpgradePayment.created_at.desc())
        .limit(40)
    ).all()
    plans = {row.id: row for row in db.scalars(select(MiningPlan).where(MiningPlan.organization_id == org_id)).all()}
    return [_payment_payload(row, plans.get(row.plan_id)) for row in rows]


def list_reward_rows(db: Session, org_id, user_id, limit: int = 40) -> list[dict]:
    rows = db.scalars(
        select(MiningRewardLedger)
        .where(MiningRewardLedger.organization_id == org_id, MiningRewardLedger.user_id == user_id)
        .order_by(MiningRewardLedger.created_at.desc())
        .limit(limit)
    ).all()
    return [_ledger_payload(row) for row in rows]


def hybrid_overview(db: Session, org_id, user_id) -> dict:
    ensure_plans(db, org_id)
    accrue_user(db, org_id, user_id)
    settings = _settings(db, org_id)
    base = _dec(settings.base_daily_pcoin, "base daily PCoin")
    upgrade = active_upgrade(db, org_id, user_id)
    plan = db.get(MiningPlan, upgrade.plan_id) if upgrade else free_plan(db, org_id)
    multiplier = _multiplier(upgrade.multiplier if upgrade else "1")
    bonus = bonus_available(db, org_id, user_id)
    now = _now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)
    pow_today = _pow_since(db, org_id, user_id, today)
    return {
        "paused": settings.paused,
        "required": False,
        "plan": _plan_payload(db, plan, org_id, user_id) if plan else None,
        "multiplier": str(multiplier),
        "base_daily": format(base, "f"),
        "speed_daily": format((base * multiplier).quantize(_SCALE, rounding=ROUND_DOWN), "f"),
        "mining": "running" if _session_running(org_id, user_id) else "stopped",
        "expires_at": upgrade.ends_at.isoformat() if upgrade and upgrade.ends_at else "",
        "started_at": upgrade.started_at.isoformat() if upgrade else "",
        "premium_available": format_amount(bonus),
        "premium_lifetime": format_amount(_credits_since(db, org_id, user_id)),
        "today_premium": format_amount(_credits_since(db, org_id, user_id, today)),
        "week_premium": format_amount(_credits_since(db, org_id, user_id, week)),
        "month_premium": format_amount(_credits_since(db, org_id, user_id, month)),
        "today_pow": format_amount(pow_today),
        "today_total": format_amount(pow_today + _credits_since(db, org_id, user_id, today)),
        "week_total": format_amount(_pow_since(db, org_id, user_id, week) + _credits_since(db, org_id, user_id, week)),
        "month_total": format_amount(_pow_since(db, org_id, user_id, month) + _credits_since(db, org_id, user_id, month)),
        "purchases": list_upgrade_payments(db, org_id, user_id)[:8],
        "rewards": list_reward_rows(db, org_id, user_id, 8),
        "detail": "Free proof-of-work mining is unchanged. A paid plan adds extra PCoin only while mining is running, using elapsed time. PCoin is not USDT until a verified conversion.",
    }


def _pow_since(db: Session, org_id, user_id, start: datetime) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(ChainHit.reward), 0)).where(
            ChainHit.organization_id == org_id,
            ChainHit.user_id == user_id,
            ChainHit.found_at >= start,
        )
    )
    return int(total or 0)


def _payment_payload(row: MiningUpgradePayment, plan: MiningPlan | None) -> dict:
    return {
        "id": str(row.id),
        "reference": row.reference,
        "plan": plan.name if plan else "",
        "plan_id": str(row.plan_id),
        "amount": format(row.amount, "f"),
        "currency": row.currency,
        "method": row.method,
        "status": row.status,
        "invoice_url": row.invoice_url,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "paid_at": row.paid_at.isoformat() if row.paid_at else "",
    }


def _upgrade_payload(row: UserMiningUpgrade, plan: MiningPlan | None) -> dict:
    return {
        "id": str(row.id),
        "plan": plan.name if plan else "",
        "multiplier": row.multiplier,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else "",
        "ends_at": row.ends_at.isoformat() if row.ends_at else "",
    }


def _ledger_payload(row: MiningRewardLedger) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "amount": format_amount(int(row.amount_atomic)),
        "multiplier": row.multiplier,
        "reference": row.reference,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def settings_payload(db: Session, org_id) -> dict:
    ensure_plans(db, org_id)
    row = _settings(db, org_id)
    return {
        "paused": row.paused,
        "base_daily_pcoin": row.base_daily_pcoin,
        "default_duration_days": row.default_duration_days,
        "max_multiplier": row.max_multiplier,
    }


def update_settings(db: Session, org_id, actor_id, payload: dict) -> dict:
    row = _settings(db, org_id)
    before = settings_payload(db, org_id)
    if "paused" in payload:
        row.paused = bool(payload["paused"])
    if payload.get("base_daily_pcoin") not in (None, ""):
        value = _dec(payload["base_daily_pcoin"], "base daily PCoin")
        if value <= 0:
            raise MiningPlanError(400, "Base daily PCoin must be greater than zero")
        row.base_daily_pcoin = format(value.quantize(_SCALE, rounding=ROUND_DOWN), "f")
    if payload.get("default_duration_days") not in (None, ""):
        days = int(payload["default_duration_days"])
        if days < 0:
            raise MiningPlanError(400, "Duration cannot be negative")
        row.default_duration_days = days
    if payload.get("max_multiplier") not in (None, ""):
        row.max_multiplier = str(_multiplier(payload["max_multiplier"]))
    write_audit(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        action="mining_settings_updated",
        entity_type="mining_settings",
        entity_id=str(org_id),
        before=before,
        after=settings_payload(db, org_id),
    )
    return settings_payload(db, org_id)


def save_plan(db: Session, org_id, actor_id, payload: dict, plan_id: str | None = None) -> dict:
    ensure_plans(db, org_id)
    settings = _settings(db, org_id)
    if plan_id:
        try:
            plan = db.get(MiningPlan, UUID(str(plan_id)))
        except (TypeError, ValueError) as exc:
            raise MiningPlanError(400, "Unknown mining plan") from exc
        if plan is None or plan.organization_id != org_id:
            raise MiningPlanError(404, "Unknown mining plan")
        if plan.code == "free" and payload.get("enabled") is False:
            raise MiningPlanError(400, "The free miner cannot be disabled")
    else:
        code = str(payload.get("code") or "").strip().lower()
        if not code:
            raise MiningPlanError(400, "Enter a plan code")
        plan = MiningPlan(organization_id=org_id, code=code[:32])
        db.add(plan)
        db.flush()
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise MiningPlanError(400, "Enter a plan name")
        plan.name = name[:80]
    if "price" in payload:
        plan.price = _dec(payload["price"], "price").quantize(_SCALE, rounding=ROUND_DOWN)
    if "multiplier" in payload:
        multiplier = _multiplier(payload["multiplier"])
        if multiplier > _multiplier(settings.max_multiplier):
            raise MiningPlanError(400, "Multiplier is above the maximum upgrade level")
        plan.multiplier = str(multiplier)
    if "duration_days" in payload:
        days = int(payload["duration_days"])
        if days < 0:
            raise MiningPlanError(400, "Duration cannot be negative")
        if plan.code == "free":
            days = 0
        plan.duration_days = days
    if "daily_limit" in payload:
        limit = str(payload.get("daily_limit") or "0").strip() or "0"
        if limit != "0":
            parse_amount(limit)
        plan.daily_limit = limit
    if "benefits" in payload:
        plan.benefits = str(payload.get("benefits") or "")[:2000]
    if "enabled" in payload:
        plan.enabled = bool(payload["enabled"])
    if "sort_order" in payload:
        plan.sort_order = int(payload["sort_order"])
    write_audit(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        action="mining_plan_saved",
        entity_type="mining_plan",
        entity_id=str(plan.id),
        after={"code": plan.code, "price": format(plan.price, "f"), "multiplier": plan.multiplier, "enabled": plan.enabled},
    )
    return _plan_payload(db, plan, org_id, actor_id)


def admin_overview(db: Session, org_id) -> dict:
    ensure_plans(db, org_id)
    now = _now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)
    wallets = db.scalars(select(ChainWallet).where(ChainWallet.organization_id == org_id)).all()
    upgrades = db.scalars(select(UserMiningUpgrade).where(UserMiningUpgrade.organization_id == org_id, UserMiningUpgrade.status == "active")).all()
    live = []
    for row in upgrades:
        if row.ends_at is not None and row.ends_at <= now:
            row.status = "expired"
            continue
        live.append(row)
    premium_ids = {row.user_id for row in live}
    issued = db.scalar(select(func.coalesce(func.sum(MiningRewardLedger.amount_atomic), 0)).where(MiningRewardLedger.organization_id == org_id, MiningRewardLedger.amount_atomic > 0))
    pow_total = db.scalar(select(func.coalesce(func.sum(ChainHit.reward), 0)).where(ChainHit.organization_id == org_id))
    def window(start: datetime) -> dict:
        premium = db.scalar(select(func.coalesce(func.sum(MiningRewardLedger.amount_atomic), 0)).where(MiningRewardLedger.organization_id == org_id, MiningRewardLedger.created_at >= start, MiningRewardLedger.amount_atomic > 0))
        mined = db.scalar(select(func.coalesce(func.sum(ChainHit.reward), 0)).where(ChainHit.organization_id == org_id, ChainHit.found_at >= start))
        return {"premium": format_amount(int(premium or 0)), "pow": format_amount(int(mined or 0)), "total": format_amount(int(premium or 0) + int(mined or 0))}
    purchases = db.scalars(select(MiningUpgradePayment).where(MiningUpgradePayment.organization_id == org_id).order_by(MiningUpgradePayment.created_at.desc()).limit(30)).all()
    plans = {row.id: row for row in db.scalars(select(MiningPlan).where(MiningPlan.organization_id == org_id)).all()}
    return {
        "settings": settings_payload(db, org_id),
        "free_miners": len([row for row in wallets if row.user_id not in premium_ids]),
        "premium_miners": len(premium_ids),
        "wallets": len(wallets),
        "pcoin_issued_premium": format_amount(int(issued or 0)),
        "pcoin_issued_pow": format_amount(int(pow_total or 0)),
        "pcoin_issued_total": format_amount(int(issued or 0) + int(pow_total or 0)),
        "today": window(today),
        "week": window(week),
        "month": window(month),
        "purchases": [_payment_payload(row, plans.get(row.plan_id)) for row in purchases],
    }


def admin_miners(db: Session, org_id) -> dict:
    users = {row.id: row for row in db.scalars(select(User).where(User.organization_id == org_id)).all()}
    wallets = db.scalars(select(ChainWallet).where(ChainWallet.organization_id == org_id)).all()
    plans = {row.id: row for row in db.scalars(select(MiningPlan).where(MiningPlan.organization_id == org_id)).all()}
    premium = []
    free = []
    for wallet in wallets:
        user = users.get(wallet.user_id)
        upgrade = active_upgrade(db, org_id, wallet.user_id)
        plan = db.get(MiningPlan, upgrade.plan_id) if upgrade else free_plan(db, org_id)
        item = {
            "user_id": str(wallet.user_id),
            "email": user.email if user else "",
            "address": wallet.address,
            "plan": plan.name if plan else "Free Miner",
            "multiplier": upgrade.multiplier if upgrade else "1",
            "expires_at": upgrade.ends_at.isoformat() if upgrade and upgrade.ends_at else "",
            "premium": format_amount(bonus_available(db, org_id, wallet.user_id)),
            "mining": "running" if _session_running(org_id, wallet.user_id) else "stopped",
        }
        if upgrade:
            premium.append(item)
        else:
            free.append(item)
    return {"premium": premium, "free": free, "plans": [_plan_payload(db, row, org_id, org_id) for row in plans.values()]}


def admin_suspicious(db: Session, org_id) -> list[dict]:
    settings = _settings(db, org_id)
    base = _dec(settings.base_daily_pcoin, "base daily PCoin")
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    upgrades = db.scalars(select(UserMiningUpgrade).where(UserMiningUpgrade.organization_id == org_id, UserMiningUpgrade.status == "active")).all()
    for upgrade in upgrades:
        credited = _credits_since(db, org_id, upgrade.user_id, today)
        expected = extra_atomic(base, _multiplier(upgrade.multiplier), 86400)
        if expected and credited > int(expected * 1.5):
            user = db.get(User, upgrade.user_id)
            rows.append(
                {
                    "user_id": str(upgrade.user_id),
                    "email": user.email if user else "",
                    "credited_today": format_amount(credited),
                    "expected_today": format_amount(expected),
                    "multiplier": upgrade.multiplier,
                    "reason": "Premium credits exceeded 1.5x the configured daily extra",
                }
            )
    return rows
