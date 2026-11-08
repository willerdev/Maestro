from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Principal, get_principal
from app.services.pocket_browser import PocketLoginError, close_login, login_status, open_login

router = APIRouter()


@router.post("/connections/pocketoption/login")
def start_pocket_login(principal: Principal = Depends(get_principal)):
    principal.require("accounts.connect")
    try:
        session = open_login(str(principal.user.id))
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
