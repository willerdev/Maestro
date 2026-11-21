"""Double-entry journal for money the desk has already recorded.

Wallet balances stay on asset transfers. This journal only records the same
posted movements so the books can be checked. A source key can be posted once.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AssetTransfer, LedgerAccount, LedgerJournal, LedgerLine

logger = logging.getLogger(__name__)

CHART: dict[str, tuple[str, str, str]] = {
    "1000": ("Cash", "asset", "debit"),
    "1100": ("Subscriptions receivable", "asset", "debit"),
    "2100": ("Investor capital", "liability", "credit"),
    "2200": ("Redemptions payable", "liability", "credit"),
    "4100": ("Fee income", "income", "credit"),
}


class LedgerError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


def ensure_ledger_tables(db: Session) -> None:
    bind = db.get_bind()
    LedgerAccount.__table__.create(bind=bind, checkfirst=True)
    LedgerJournal.__table__.create(bind=bind, checkfirst=True)
    LedgerLine.__table__.create(bind=bind, checkfirst=True)


def post(db: Session, organization_id, source_key: str, memo: str, lines: list[tuple[str, Decimal, Decimal, str]]) -> LedgerJournal:
    ensure_ledger_tables(db)
    key = source_key.strip()[:80]
    existing = db.scalar(select(LedgerJournal).where(LedgerJournal.organization_id == organization_id, LedgerJournal.source_key == key))
    if existing is not None:
        return existing
    if not lines:
        raise LedgerError("A journal needs lines")
    totals: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    cleaned: list[tuple[str, Decimal, Decimal, str]] = []
    for code, debit, credit, currency in lines:
        if code not in CHART:
            raise LedgerError("Unknown ledger account")
        debit = Decimal(debit)
        credit = Decimal(credit)
        if debit < 0 or credit < 0 or (debit == 0 and credit == 0) or (debit > 0 and credit > 0):
            raise LedgerError("Each line is a debit or a credit")
        coin = str(currency or "").strip().upper()[:16]
        if not coin:
            raise LedgerError("Each line needs a currency")
        totals[coin][0] += debit
        totals[coin][1] += credit
        cleaned.append((code, debit, credit, coin))
    for debit, credit in totals.values():
        if debit != credit:
            raise LedgerError("Debits and credits must match")
    journal = LedgerJournal(organization_id=organization_id, source_key=key, memo=memo[:240], status="posted")
    db.add(journal)
    db.flush()
    for code, debit, credit, coin in cleaned:
        account = _account(db, organization_id, code)
        db.add(LedgerLine(journal_id=journal.id, account_id=account.id, debit=debit, credit=credit, currency=coin))
    db.flush()
    return journal


def record_safely(db: Session, organization_id, source_key: str, memo: str, lines: list[tuple[str, Decimal, Decimal, str]]) -> None:
    try:
        with db.begin_nested():
            post(db, organization_id, source_key, memo, lines)
    except Exception:
        logger.exception("ledger_post_failed")


def post_asset_transfer(db: Session, row: AssetTransfer) -> None:
    if row.status != "posted":
        return
    # An operating charge moves spendable balance between logins inside custody.
    # It is not new cash and it is not a withdrawal, so the org cash account stays put.
    note = str(row.note or "")
    if row.direction == "expense" or note.startswith("Operating expense from"):
        return
    amount = Decimal(row.amount)
    if amount <= 0:
        return
    coin = str(row.currency or "USD")
    key = f"asset:{row.id}"
    if row.direction == "deposit":
        record_safely(db, row.organization_id, key, "Wallet deposit posted", [("1000", amount, Decimal("0"), coin), ("2100", Decimal("0"), amount, coin)])
    elif row.direction == "withdraw":
        record_safely(db, row.organization_id, key, "Wallet withdrawal posted", [("2100", amount, Decimal("0"), coin), ("1000", Decimal("0"), amount, coin)])


def sync_posted_transfers(db: Session, organization_id) -> None:
    ensure_ledger_tables(db)
    rows = db.scalars(
        select(AssetTransfer).where(
            AssetTransfer.organization_id == organization_id,
            AssetTransfer.status == "posted",
            AssetTransfer.direction.in_(("deposit", "withdraw", "expense")),
        )
    ).all()
    for row in rows:
        post_asset_transfer(db, row)


def ledger_view(db: Session, organization_id) -> dict:
    sync_posted_transfers(db, organization_id)
    accounts = db.scalars(select(LedgerAccount).where(LedgerAccount.organization_id == organization_id).order_by(LedgerAccount.code)).all()
    lines = []
    if accounts:
        ids = [row.id for row in accounts]
        lines = db.scalars(select(LedgerLine).where(LedgerLine.account_id.in_(ids))).all()
    grouped: dict[str, list[LedgerLine]] = defaultdict(list)
    for line in lines:
        grouped[str(line.account_id)].append(line)
    books = []
    debit_total = Decimal("0")
    credit_total = Decimal("0")
    for account in accounts:
        debit = sum((line.debit for line in grouped[str(account.id)]), Decimal("0"))
        credit = sum((line.credit for line in grouped[str(account.id)]), Decimal("0"))
        debit_total += debit
        credit_total += credit
        balance = debit - credit if account.normal == "debit" else credit - debit
        books.append(
            {
                "code": account.code,
                "name": account.name,
                "kind": account.kind,
                "debit": format(debit, "f"),
                "credit": format(credit, "f"),
                "balance": format(balance, "f"),
            }
        )
    journals = db.scalars(select(LedgerJournal).where(LedgerJournal.organization_id == organization_id).order_by(LedgerJournal.created_at.desc()).limit(40)).all()
    return {
        "balanced": debit_total == credit_total,
        "accounts": books,
        "journals": [{"id": str(row.id), "memo": row.memo, "status": row.status, "created_at": row.created_at.isoformat()} for row in journals],
    }


def _account(db: Session, organization_id, code: str) -> LedgerAccount:
    row = db.scalar(select(LedgerAccount).where(LedgerAccount.organization_id == organization_id, LedgerAccount.code == code))
    if row is not None:
        return row
    name, kind, normal = CHART[code]
    row = LedgerAccount(organization_id=organization_id, code=code, name=name, kind=kind, normal=normal)
    db.add(row)
    db.flush()
    return row
