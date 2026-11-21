"""Record PCoin to internal USDT conversions. Balances are sums of these rows, not edited in place."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chain.convert import ConversionError, format_usdt, quote_conversion
from app.chain.money import format_amount
from app.models.chain_entities import ChainConversion, ChainConversionSettings, ChainRateChange, ChainWallet
from app.models.entities import AssetTransfer, User


class ConversionServiceError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def _defaults() -> dict:
    return {"enabled": True, "rate": "1000", "min_pcoin": "1000", "max_pcoin": "0", "fee_bps": 0}


def settings_row(db: Session, org_id) -> ChainConversionSettings | None:
    return db.get(ChainConversionSettings, org_id)


def public_settings(db: Session, org_id) -> dict:
    row = settings_row(db, org_id)
    data = _defaults()
    if row is not None:
        data = {"enabled": row.enabled, "rate": row.rate, "min_pcoin": row.min_pcoin, "max_pcoin": row.max_pcoin, "fee_bps": row.fee_bps}
    data["label"] = f"{data['rate']} PCoin = 1 USDT TRC20"
    data["usdt_kind"] = "trc20"
    data["network"] = "trc20"
    data["detail"] = "Mined PCoin converts at 1000 PCoin = 1 USDT and is credited to the default wallet as USDT TRC20. The PCoin is deducted and held as converted."
    return data


def pcoin_hold(db: Session, org_id, user_id) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(ChainConversion.pcoin_atomic + ChainConversion.fee_atomic), 0)).where(
            ChainConversion.organization_id == org_id,
            ChainConversion.user_id == user_id,
            ChainConversion.status == "completed",
        )
    )
    return int(total or 0)


def usdt_balance(db: Session, org_id, user_id) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(ChainConversion.usdt_atomic), 0)).where(
            ChainConversion.organization_id == org_id,
            ChainConversion.user_id == user_id,
            ChainConversion.status == "completed",
        )
    )
    return int(total or 0)


def _spendable(db: Session, org_id, user_id) -> int:
    from app.services.chain_service import load_ledger

    wallet = db.scalar(select(ChainWallet).where(ChainWallet.organization_id == org_id, ChainWallet.user_id == user_id))
    if wallet is None:
        return 0
    ledger = load_ledger(db, org_id)
    from app.services.mining_plan_service import bonus_available

    from app.services.pcoin_approval_service import held_pcoin_atomic

    return max(0, ledger.available(wallet.address) - pcoin_hold(db, org_id, user_id) + bonus_available(db, org_id, user_id) - held_pcoin_atomic(db, org_id, user_id))


def _public_conversion(row: ChainConversion) -> dict:
    return {
        "reference": row.reference,
        "pcoin": format_amount(int(row.pcoin_atomic)),
        "fee": format_amount(int(row.fee_atomic)),
        "usdt": format_usdt(int(row.usdt_atomic)),
        "rate": row.rate,
        "status": row.status,
        "network": row.network,
        "created_at": row.created_at.isoformat(),
    }


def preview(db: Session, org_id, user_id, amount: str) -> dict:
    rules = public_settings(db, org_id)
    try:
        quoted = quote_conversion(
            amount,
            available=_spendable(db, org_id, user_id),
            rate=rules["rate"],
            fee_bps=int(rules["fee_bps"]),
            min_pcoin=rules["min_pcoin"],
            max_pcoin=rules["max_pcoin"],
            enabled=bool(rules["enabled"]),
        )
    except ConversionError as exc:
        raise ConversionServiceError(400, str(exc)) from exc
    return {
        "pcoin": format_amount(quoted.pcoin_atomic),
        "fee": format_amount(quoted.fee_atomic),
        "total_pcoin": format_amount(quoted.cost_atomic),
        "usdt": format_usdt(quoted.usdt_atomic),
        "rate": quoted.rate,
        "available_pcoin": format_amount(_spendable(db, org_id, user_id)),
    }


def convert(db: Session, org_id, user_id, amount: str, reference: str = "") -> dict:
    from app.services.chain_service import _lock

    ref = reference.strip() or f"PC{uuid.uuid4().hex[:16]}"
    if len(ref) > 40:
        raise ConversionServiceError(400, "The reference is too long")
    with _lock(org_id):
        wallet = db.scalar(select(ChainWallet).where(ChainWallet.organization_id == org_id, ChainWallet.user_id == user_id).with_for_update())
        if wallet is None:
            raise ConversionServiceError(404, "Create a Project Coin wallet first")
        existing = db.scalar(select(ChainConversion).where(ChainConversion.organization_id == org_id, ChainConversion.reference == ref))
        if existing is not None:
            if existing.user_id != user_id:
                raise ConversionServiceError(409, "That reference is already used")
            return {**_public_conversion(existing), "duplicate": True, **_balances(db, org_id, user_id)}
        rules = public_settings(db, org_id)
        try:
            quoted = quote_conversion(
                amount,
                available=_spendable(db, org_id, user_id),
                rate=rules["rate"],
                fee_bps=int(rules["fee_bps"]),
                min_pcoin=rules["min_pcoin"],
                max_pcoin=rules["max_pcoin"],
                enabled=bool(rules["enabled"]),
            )
        except ConversionError as exc:
            raise ConversionServiceError(400, str(exc)) from exc
        row = ChainConversion(
            organization_id=org_id,
            user_id=user_id,
            reference=ref,
            pcoin_atomic=quoted.pcoin_atomic,
            fee_atomic=quoted.fee_atomic,
            usdt_atomic=quoted.usdt_atomic,
            rate=quoted.rate,
            status="completed",
            network="trc20",
        )
        db.add(row)
        _credit_default_wallet(db, org_id, user_id, quoted.usdt_atomic, ref)
        db.commit()
        db.refresh(row)
    return {**_public_conversion(row), "duplicate": False, **_balances(db, org_id, user_id)}


def _credit_default_wallet(db: Session, org_id, user_id, usdt_atomic: int, reference: str) -> None:
    from decimal import Decimal, ROUND_DOWN

    from app.chain.convert import USDT_UNIT

    cash = (Decimal(usdt_atomic) / Decimal(USDT_UNIT)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
    if cash <= 0:
        return
    existing = db.scalar(
        select(AssetTransfer).where(
            AssetTransfer.organization_id == org_id,
            AssetTransfer.user_id == user_id,
            AssetTransfer.order_id == reference,
            AssetTransfer.direction == "deposit",
        )
    )
    if existing is not None:
        return
    db.add(
        AssetTransfer(
            organization_id=org_id,
            user_id=user_id,
            currency="usdttrc20",
            direction="deposit",
            amount=cash,
            status="posted",
            note=f"PCoin conversion {reference}",
            order_id=reference,
        )
    )


def _balances(db: Session, org_id, user_id) -> dict:
    return {
        "available_pcoin": format_amount(_spendable(db, org_id, user_id)),
        "available_usdt": format_usdt(usdt_balance(db, org_id, user_id)),
        "converted_pcoin": format_amount(pcoin_hold(db, org_id, user_id)),
    }


def wallet_conversion(db: Session, org_id, user_id) -> dict:
    rules = public_settings(db, org_id)
    rows = list(
        db.scalars(
            select(ChainConversion)
            .where(ChainConversion.organization_id == org_id, ChainConversion.user_id == user_id)
            .order_by(ChainConversion.created_at.desc())
            .limit(20)
        )
    )
    return {**_balances(db, org_id, user_id), "settings": rules, "history": [_public_conversion(row) for row in rows]}


def list_conversions(db: Session, org_id, limit: int = 100) -> list[dict]:
    rows = db.execute(
        select(ChainConversion, User.email)
        .join(User, User.id == ChainConversion.user_id)
        .where(ChainConversion.organization_id == org_id)
        .order_by(ChainConversion.created_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    items = []
    for conversion, email in rows:
        item = _public_conversion(conversion)
        item["email"] = email
        items.append(item)
    return items


def report(db: Session, org_id) -> dict:
    pcoin = int(db.scalar(select(func.coalesce(func.sum(ChainConversion.pcoin_atomic), 0)).where(ChainConversion.organization_id == org_id, ChainConversion.status == "completed")) or 0)
    usdt = int(db.scalar(select(func.coalesce(func.sum(ChainConversion.usdt_atomic), 0)).where(ChainConversion.organization_id == org_id, ChainConversion.status == "completed")) or 0)
    count = int(db.scalar(select(func.count()).select_from(ChainConversion).where(ChainConversion.organization_id == org_id)) or 0)
    return {"conversions": count, "pcoin_converted": format_amount(pcoin), "usdt_credited": format_usdt(usdt), "settings": public_settings(db, org_id)}


def export_csv(db: Session, org_id) -> str:
    lines = ["reference,email,pcoin,fee,usdt,rate,status,network,created_at"]
    for item in list_conversions(db, org_id, limit=500):
        lines.append(",".join([item["reference"], item["email"], item["pcoin"], item["fee"], item["usdt"], item["rate"], item["status"], item["network"], item["created_at"]]))
    return "\n".join(lines) + "\n"


def update_settings(db: Session, org_id, actor_id, *, rate: str, enabled: bool, min_pcoin: str, max_pcoin: str, fee_bps: int) -> dict:
    from app.chain.convert import parse_rate

    try:
        parse_rate(rate)
        if str(min_pcoin) not in {"", "0", "0.0"}:
            from app.chain.money import parse_amount

            parse_amount(min_pcoin)
        if str(max_pcoin) not in {"", "0", "0.0"}:
            from app.chain.money import parse_amount

            parse_amount(max_pcoin)
    except (ConversionError, ValueError) as exc:
        raise ConversionServiceError(400, str(exc)) from exc
    if int(fee_bps) < 0 or int(fee_bps) > 10_000:
        raise ConversionServiceError(400, "The conversion fee is invalid")
    current = settings_row(db, org_id)
    old_rate = current.rate if current else "1000"
    old_enabled = current.enabled if current else True
    if current is None:
        current = ChainConversionSettings(organization_id=org_id)
        db.add(current)
    current.rate = str(rate).strip()
    current.enabled = bool(enabled)
    current.min_pcoin = str(min_pcoin).strip() or "0"
    current.max_pcoin = str(max_pcoin).strip() or "0"
    current.fee_bps = int(fee_bps)
    current.updated_at = datetime.now(timezone.utc)
    db.add(ChainRateChange(organization_id=org_id, actor_user_id=actor_id, old_rate=old_rate, new_rate=current.rate, old_enabled=old_enabled, new_enabled=current.enabled))
    db.commit()
    return public_settings(db, org_id)
