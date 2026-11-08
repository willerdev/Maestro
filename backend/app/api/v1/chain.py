"""Authenticated Project Coin routes. Rewards are created only by a validated block."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, get_principal
from app.core.rate_limit import WindowLimiter
from app.services.chain_service import ChainServiceError, block_detail, create_wallet, export_wallet, import_wallet, list_blocks, list_transactions, mining_statistics, mining_status, network_status, pause_mining, resume_mining, search, send_coins, start_mining, stop_mining, transaction_detail, wallet_transactions, wallet_view

router = APIRouter(prefix="/chain")
_limiter = WindowLimiter()


class WalletImport(BaseModel):
    private_key: str = Field(min_length=64, max_length=64)


class WalletExport(BaseModel):
    confirm: bool = False


class SendBody(BaseModel):
    recipient: str
    amount: str


class MineBody(BaseModel):
    cpu_percent: int | None = None


def _run(func):
    try:
        return func()
    except ChainServiceError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


def _guard(principal: Principal, action: str) -> None:
    if _limiter.hit(f"{principal.user.id}:{action}", limit=20, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many chain requests. Wait a minute.")


@router.post("/wallet")
def create(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "wallet")
    return _run(lambda: create_wallet(db, principal.user.organization_id, principal.user.id))


@router.post("/wallet/import")
def import_key(body: WalletImport, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "import")
    return _run(lambda: import_wallet(db, principal.user.organization_id, principal.user.id, body.private_key))


@router.post("/wallet/export")
def export_key(body: WalletExport, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirm the export before the private key is shown")
    _guard(principal, "export")
    return _run(lambda: export_wallet(db, principal.user.organization_id, principal.user.id))


@router.get("/wallet")
def wallet(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: wallet_view(db, principal.user.organization_id, principal.user.id))


@router.get("/wallet/balance")
def balance(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    view = _run(lambda: wallet_view(db, principal.user.organization_id, principal.user.id))
    return {"available": view["available"], "pending": view["pending"], "confirmed": view["confirmed"], "symbol": view["symbol"]}


@router.get("/wallet/transactions")
def mine_wallet_transactions(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: wallet_transactions(db, principal.user.organization_id, principal.user.id))


@router.post("/wallet/send")
def send(body: SendBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "send")
    return _run(lambda: send_coins(db, principal.user.organization_id, principal.user.id, body.recipient.strip().lower(), body.amount))


@router.post("/mining/start")
def start(body: MineBody | None = None, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "start")
    cpu = body.cpu_percent if body else None
    return _run(lambda: start_mining(db, principal.user.organization_id, principal.user.id, cpu))


@router.post("/mining/stop")
def stop(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    return _run(lambda: stop_mining(db, principal.user.organization_id, principal.user.id))


@router.post("/mining/pause")
def pause(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    return _run(lambda: pause_mining(db, principal.user.organization_id, principal.user.id))


@router.post("/mining/resume")
def resume(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    return _run(lambda: resume_mining(db, principal.user.organization_id, principal.user.id))


@router.get("/mining/status")
def status(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: mining_status(db, principal.user.organization_id, principal.user.id))


@router.get("/mining/statistics")
def statistics(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: mining_statistics(db, principal.user.organization_id, principal.user.id))


@router.get("/blocks")
def blocks(limit: int = Query(default=50, ge=1, le=200), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: list_blocks(db, principal.user.organization_id, limit))


@router.get("/blocks/{height}")
def one_block(height: int, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: block_detail(db, principal.user.organization_id, height))


@router.get("/transactions")
def transactions(limit: int = Query(default=50, ge=1, le=200), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: list_transactions(db, principal.user.organization_id, limit))


@router.get("/transactions/{tx_hash}")
def one_transaction(tx_hash: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: transaction_detail(db, principal.user.organization_id, tx_hash.strip().lower()))


@router.get("/search")
def find(q: str = Query(min_length=1, max_length=80), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: search(db, principal.user.organization_id, q))


@router.get("/network/status")
def network(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: network_status(db, principal.user.organization_id))
