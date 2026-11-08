from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, get_principal
from app.core.rate_limit import WindowLimiter
from app.services.extra_wallet_service import ExtraWalletError, delete_extra_wallet, list_extra_wallets, save_extra_wallet

router = APIRouter()
_limiter = WindowLimiter()


class ExtraWalletIn(BaseModel):
    private_key: str = ""
    address: str = ""


def _run(func):
    try:
        return func()
    except ExtraWalletError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/wallets/extra")
def list_wallets(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("accounts.read")
    return list_extra_wallets(db, principal.user.organization_id, principal.user.id)


@router.put("/wallets/extra/{provider}")
def save_wallet(provider: str, body: ExtraWalletIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("accounts.write")
    if _limiter.hit(f"extra:{principal.user.id}", limit=10, window_seconds=60):
        raise HTTPException(429, "Too many wallet saves")
    result = _run(lambda: save_extra_wallet(db, principal.user.organization_id, principal.user.id, provider.lower(), body.model_dump()))
    db.commit()
    return result


@router.delete("/wallets/extra/{provider}")
def remove_wallet(provider: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("accounts.write")
    _run(lambda: delete_extra_wallet(db, principal.user.organization_id, principal.user.id, provider.lower()))
    db.commit()
    return {"ok": True}
