"""Project Coin credits stay out of the spendable wallet until an admin approves them.

Existing credits are marked approved the first time this runs, so current balances stay put.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chain.money import format_amount
from app.domain.audit import write_audit
from app.domain.rbac import allows
from app.models.chain_entities import ChainTxRow, ChainWallet, MiningRewardLedger, PcoinCreditApproval
from app.models.entities import User


class PcoinApprovalError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def ensure_credit_table(db: Session) -> None:
    PcoinCreditApproval.__table__.create(bind=db.get_bind(), checkfirst=True)


def sync_pcoin_credits(db: Session, organization_id, actor_user_id) -> None:
    ensure_credit_table(db)
    seeded = db.scalar(
        select(PcoinCreditApproval.id).where(
            PcoinCreditApproval.organization_id == organization_id,
            PcoinCreditApproval.source == "marker",
            PcoinCreditApproval.source_key == "seed",
        )
    )
    known = {
        (row.source, row.source_key)
        for row in db.scalars(select(PcoinCreditApproval).where(PcoinCreditApproval.organization_id == organization_id)).all()
    }
    status = "approved" if seeded is None else "pending"
    wallets = {
        row.address: row.user_id
        for row in db.scalars(select(ChainWallet).where(ChainWallet.organization_id == organization_id)).all()
    }
    rewards = db.scalars(
        select(ChainTxRow).where(
            ChainTxRow.organization_id == organization_id,
            ChainTxRow.kind.in_(("reward", "transfer")),
            ChainTxRow.block_height.is_not(None),
            ChainTxRow.amount > 0,
        )
    ).all()
    for row in rewards:
        user_id = wallets.get(row.recipient)
        if user_id is None or ("chain", str(row.id)) in known:
            continue
        db.add(
            PcoinCreditApproval(
                organization_id=organization_id,
                user_id=user_id,
                source="chain",
                source_key=str(row.id),
                amount_atomic=int(row.amount),
                status=status,
            )
        )
        known.add(("chain", str(row.id)))
    premiums = db.scalars(
        select(MiningRewardLedger).where(
            MiningRewardLedger.organization_id == organization_id,
            MiningRewardLedger.amount_atomic > 0,
        )
    ).all()
    for row in premiums:
        if ("premium", str(row.id)) in known:
            continue
        db.add(
            PcoinCreditApproval(
                organization_id=organization_id,
                user_id=row.user_id,
                source="premium",
                source_key=str(row.id),
                amount_atomic=int(row.amount_atomic),
                status=status,
            )
        )
        known.add(("premium", str(row.id)))
    if seeded is None:
        db.add(
            PcoinCreditApproval(
                organization_id=organization_id,
                user_id=actor_user_id,
                source="marker",
                source_key="seed",
                amount_atomic=0,
                status="approved",
            )
        )
    db.flush()


def held_pcoin_atomic(db: Session, organization_id, user_id) -> int:
    sync_pcoin_credits(db, organization_id, user_id)
    total = db.scalar(
        select(func.coalesce(func.sum(PcoinCreditApproval.amount_atomic), 0)).where(
            PcoinCreditApproval.organization_id == organization_id,
            PcoinCreditApproval.user_id == user_id,
            PcoinCreditApproval.status.in_(("pending", "rejected")),
        )
    )
    return max(0, int(total or 0))


def list_pending_credits(db: Session, actor: User, roles: list[str]) -> list[dict]:
    _require_admin(roles)
    sync_pcoin_credits(db, actor.organization_id, actor.id)
    query = select(PcoinCreditApproval).where(PcoinCreditApproval.status == "pending").order_by(PcoinCreditApproval.created_at.desc()).limit(200)
    if "SUPER_ADMIN" not in roles:
        query = query.where(PcoinCreditApproval.organization_id == actor.organization_id)
    rows = list(db.scalars(query).all())
    users = {row.id: row for row in db.scalars(select(User).where(User.id.in_({item.user_id for item in rows}))).all()} if rows else {}
    return [_credit_payload(row, users.get(row.user_id)) for row in rows]


def decide_pcoin_credit(db: Session, actor: User, roles: list[str], credit_id, decision: str, ip: str) -> dict:
    _require_admin(roles)
    if decision not in {"approve", "reject"}:
        raise PcoinApprovalError(400, "Choose approve or reject")
    row = db.get(PcoinCreditApproval, credit_id)
    if row is None or row.source == "marker" or ("SUPER_ADMIN" not in roles and row.organization_id != actor.organization_id):
        raise PcoinApprovalError(404, "That Project Coin credit was not found")
    if row.status != "pending":
        raise PcoinApprovalError(400, "That credit is already reviewed")
    row.status = "approved" if decision == "approve" else "rejected"
    write_audit(
        db,
        organization_id=row.organization_id,
        actor_user_id=actor.id,
        action="pcoin_credit_reviewed",
        entity_type="pcoin_credit",
        entity_id=str(row.id),
        after={"decision": decision, "amount": format_amount(int(row.amount_atomic))},
        ip_address=ip,
    )
    owner = db.get(User, row.user_id)
    return _credit_payload(row, owner)


def _require_admin(roles: list[str]) -> None:
    if not allows(roles, "users.manage"):
        raise PcoinApprovalError(403, "Missing permission")


def _credit_payload(row: PcoinCreditApproval, user: User | None) -> dict:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "email": "" if user is None else user.email,
        "full_name": "" if user is None else user.full_name,
        "source": "Mining reward" if row.source == "premium" else "Project Coin",
        "amount": format_amount(int(row.amount_atomic)),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
