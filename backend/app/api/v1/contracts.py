from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, get_principal
from app.api.v1.router import _client_ip
from app.core.rate_limit import WindowLimiter
from app.services.account_service import AccountError
from app.services.contract_service import ContractServiceError, cancel_contract, desk, fund_contract, withdraw_contract

router = APIRouter()
_limiter = WindowLimiter()


class FundIn(BaseModel):
    account_id: UUID
    amount: Decimal


def _run(func):
    try:
        return func()
    except (ContractServiceError, AccountError) as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/contracts/desk")
def contract_desk(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("accounts.read")
    body = desk(db, principal.user, principal.roles)
    db.commit()
    return body


@router.post("/contracts/fund")
def post_fund(payload: FundIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("accounts.write")
    if _limiter.hit(f"contract:{principal.user.id}", limit=10, window_seconds=60):
        raise HTTPException(429, "Too many contract transfers")
    body = _run(lambda: fund_contract(db, principal.user, principal.roles, payload.account_id, payload.amount, _client_ip(request)))
    db.commit()
    return body


@router.post("/contracts/{stake_id}/cancel")
def post_cancel(stake_id: UUID, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("accounts.write")
    body = _run(lambda: cancel_contract(db, principal.user, principal.roles, stake_id, _client_ip(request)))
    db.commit()
    return body


@router.post("/contracts/{stake_id}/withdraw")
def post_withdraw(stake_id: UUID, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("accounts.write")
    body = _run(lambda: withdraw_contract(db, principal.user, principal.roles, stake_id, _client_ip(request)))
    db.commit()
    return body
