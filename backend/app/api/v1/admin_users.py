from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, get_principal
from app.api.v1.router import _client_ip
from app.services.admin_user_service import AdminUserError, allocate_wallet, set_user_banned, set_user_password, set_user_role
from app.services.asset_service import AssetError, approve_withdrawal, list_withdrawal_requests, reject_withdrawal
from app.services.license_service import LicenseError, activate_license, list_licenses

router = APIRouter()


class PasswordIn(BaseModel):
    password: str


class RoleIn(BaseModel):
    role: str


class WalletIn(BaseModel):
    amount: Decimal
    currency: str = "usdttrc20"
    purpose: str = "earnings"


class RejectIn(BaseModel):
    note: str = ""


class LicenseIn(BaseModel):
    code: str
    device_id: str = ""


def _run(func):
    try:
        return func()
    except AdminUserError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.post("/users/{user_id}/password")
def post_password(user_id: UUID, payload: PasswordIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    body = _run(lambda: set_user_password(db, principal.user, principal.roles, user_id, payload.password, _client_ip(request)))
    db.commit()
    return body


@router.post("/users/{user_id}/role")
def post_role(user_id: UUID, payload: RoleIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    body = _run(lambda: set_user_role(db, principal.user, principal.roles, user_id, payload.role, _client_ip(request)))
    db.commit()
    return body


@router.post("/users/{user_id}/ban")
def post_ban(user_id: UUID, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    body = _run(lambda: set_user_banned(db, principal.user, principal.roles, user_id, True, _client_ip(request)))
    db.commit()
    return body


@router.post("/users/{user_id}/unban")
def post_unban(user_id: UUID, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    body = _run(lambda: set_user_banned(db, principal.user, principal.roles, user_id, False, _client_ip(request)))
    db.commit()
    return body


@router.post("/users/{user_id}/wallet")
def post_wallet(user_id: UUID, payload: WalletIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    body = _run(lambda: allocate_wallet(db, principal.user, principal.roles, user_id, payload.amount, payload.currency, _client_ip(request), payload.purpose))
    db.commit()
    return body


def _asset(db: Session, func):
    try:
        return func()
    except AssetError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/licenses")
def get_licenses(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    try:
        body = list_licenses(db, principal.roles)
        db.commit()
        return body
    except LicenseError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.post("/licenses/activate")
def post_license(payload: LicenseIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    device = payload.device_id or request.headers.get("x-device-id", "")
    try:
        body = activate_license(db, principal.user, principal.roles, payload.code, device, _client_ip(request))
        db.commit()
        return body
    except LicenseError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.get("/admin/withdrawals")
def get_withdrawals(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    return list_withdrawal_requests(db, principal.user, principal.roles)


@router.post("/admin/withdrawals/{transfer_id}/approve")
def post_approve_withdrawal(transfer_id: UUID, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    body = _asset(db, lambda: approve_withdrawal(db, principal.user, principal.roles, transfer_id, _client_ip(request)))
    db.commit()
    return body


@router.post("/admin/withdrawals/{transfer_id}/reject")
def post_reject_withdrawal(transfer_id: UUID, payload: RejectIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("users.manage")
    body = _asset(db, lambda: reject_withdrawal(db, principal.user, principal.roles, transfer_id, payload.note, _client_ip(request)))
    db.commit()
    return body
