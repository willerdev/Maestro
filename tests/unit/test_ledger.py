from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import LedgerAccount, LedgerJournal, LedgerLine
from app.services.ledger_service import LedgerError, post


def _session() -> Session:
    engine = create_engine("sqlite://")
    LedgerAccount.__table__.create(engine)
    LedgerJournal.__table__.create(engine)
    LedgerLine.__table__.create(engine)
    return Session(engine)


def test_journal_balances_and_is_idempotent():
    db = _session()
    org = uuid4()
    lines = [("1000", Decimal("10"), Decimal("0"), "usdt"), ("2100", Decimal("0"), Decimal("10"), "USDT")]
    first = post(db, org, "asset:1", "Wallet deposit posted", lines)
    second = post(db, org, "asset:1", "Wallet deposit posted", lines)
    post(db, org, "asset:2", "Wallet withdrawal posted", [("2100", Decimal("4"), Decimal("0"), "USDT"), ("1000", Decimal("0"), Decimal("4"), "USDT")])
    db.commit()
    assert first.id == second.id
    assert db.query(LedgerJournal).count() == 2
    debits = sum((row.debit for row in db.query(LedgerLine)), Decimal("0"))
    credits = sum((row.credit for row in db.query(LedgerLine)), Decimal("0"))
    assert debits == credits == Decimal("14")


def test_unbalanced_journal_is_rejected():
    db = _session()
    try:
        post(db, uuid4(), "asset:3", "Broken", [("1000", Decimal("5"), Decimal("0"), "USDT"), ("2100", Decimal("0"), Decimal("4"), "USDT")])
    except LedgerError as exc:
        assert "match" in exc.detail
    else:
        raise AssertionError("unbalanced journal was accepted")
