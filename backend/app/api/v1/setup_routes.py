from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.v1.router import _account_payload, _client_ip
from app.core.database import get_db
from app.services.setup_service import SetupError, complete_setup, enable_authenticator, status_payload

router = APIRouter()


class SetupAccountIn(BaseModel):
    display_name: str = ""
    account_number: str = ""
    broker: str = ""
    server: str = ""
    connection_method: str
    currency: str = "USD"
    leverage: str = "100"
    trading_day_timezone: str = "UTC"
    credentials: dict | None = None


class SetupPaymentIn(BaseModel):
    provider: str = ""
    wallet: str = "external"
    sandbox: bool = False
    credentials: dict | None = None


class AuthenticatorIn(BaseModel):
    totp_code: str


class SetupCompleteIn(BaseModel):
    country: str
    language: str
    phone_country_code: str
    phone_number: str
    admin_email: EmailStr
    totp_code: str = ""
    account: SetupAccountIn | None = None
    payment: SetupPaymentIn | None = None


@router.get("/setup/status")
def setup_status(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    body = status_payload(db, principal.user, include_secret=True)
    db.commit()
    return body


@router.post("/setup/complete")
def setup_complete(
    payload: SetupCompleteIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    principal.require("accounts.write")
    try:
        result = complete_setup(db, principal.user, principal.roles, payload.model_dump(), _client_ip(request))
        db.commit()
    except SetupError as exc:
        db.rollback()
        raise HTTPException(exc.status, exc.detail) from exc
    body = None
    if result["account"] is not None:
        body = _account_payload(db, result["account"])
        if result["webhook"]:
            body["webhook"] = result["webhook"]
    return {"complete": True, "account": body, "connection_test": result["connection_test"]}


@router.post("/setup/authenticator")
def setup_authenticator(
    payload: AuthenticatorIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    try:
        body = enable_authenticator(db, principal.user, payload.totp_code, _client_ip(request))
        db.commit()
    except SetupError as exc:
        db.rollback()
        raise HTTPException(exc.status, exc.detail) from exc
    return body
