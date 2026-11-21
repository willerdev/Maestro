from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.core.database import get_db
from app.connectors.options_platforms import public_platforms
from app.services.account_service import AccountError, get_visible_account, set_pocket_mode
from app.services.pocket_browser import PocketLoginError, close_login, login_status, open_login

router = APIRouter()


class PocketModeIn(BaseModel):
    mode: str


class PocketLoginIn(BaseModel):
    mode: str = "real"
    platform: str = "pocketoption"


@router.get("/connections/options/platforms")
def list_options_platforms(principal: Principal = Depends(get_principal)):
    principal.require("accounts.connect")
    return {"platforms": public_platforms()}


@router.post("/connections/pocketoption/login")
def start_pocket_login(payload: PocketLoginIn, principal: Principal = Depends(get_principal)):
    principal.require("accounts.connect")
    mode = str(payload.mode or "").strip().lower()
    if mode not in {"demo", "real"}:
        raise HTTPException(400, "Choose Demo or Real")
    try:
        session = open_login(str(principal.user.id), mode, payload.platform)
    except PocketLoginError as exc:
        raise HTTPException(400, exc.detail) from exc
    return session.snapshot()


@router.get("/connections/pocketoption/login/{session_id}")
def pocket_login_status(session_id: str, principal: Principal = Depends(get_principal)):
    principal.require("accounts.connect")
    try:
        return login_status(session_id, str(principal.user.id)).snapshot()
    except PocketLoginError as exc:
        raise HTTPException(404, exc.detail) from exc


@router.delete("/connections/pocketoption/login/{session_id}")
def stop_pocket_login(session_id: str, principal: Principal = Depends(get_principal)):
    principal.require("accounts.connect")
    try:
        close_login(session_id, str(principal.user.id))
    except PocketLoginError as exc:
        raise HTTPException(404, exc.detail) from exc
    return {"closed": True}


@router.post("/accounts/{account_id}/pocketoption/mode")
def set_mode(account_id: UUID, payload: PocketModeIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    from app.api.v1.router import _account_payload, _client_ip

    principal.require("accounts.connect")
    account = get_visible_account(db, principal.user, principal.roles, account_id)
    try:
        account = set_pocket_mode(db, principal.user, account, payload.mode, _client_ip(request))
        db.commit()
    except AccountError as exc:
        db.rollback()
        raise HTTPException(exc.status, exc.detail) from exc
    body = _account_payload(db, account)
    from app.models.entities import Position
    from sqlalchemy import select

    rows = db.scalars(select(Position).where(Position.account_id == account.id, Position.status == "open")).all()
    from app.api.v1.router import _position_payload

    body["positions"] = [_position_payload(row) for row in rows]
    return body
