from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.audit import write_audit
from app.domain.rbac import allows
from app.models.entities import LicenseKey, User

POOL_SIZE = 10
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class LicenseError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def new_code() -> str:
    chunks = ["".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "MAE-" + "-".join(chunks)


def normalize_code(raw: str) -> str:
    chars = re.sub(r"[^A-Z0-9]", "", str(raw or "").upper())
    if chars.startswith("MAE"):
        chars = chars[3:]
    if len(chars) != 12:
        return ""
    return f"MAE-{chars[0:4]}-{chars[4:8]}-{chars[8:12]}"


def device_fingerprint(raw: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]", "", str(raw or ""))[:80]
    if len(text) < 8:
        return ""
    return hashlib.sha256(text.encode()).hexdigest()


def mining_device_hash(raw: str) -> str:
    return device_fingerprint(raw) or device_fingerprint("anonymous-device-id")


def computer_name(user_agent: str, fingerprint: str) -> str:
    ua = str(user_agent or "").lower()
    if "iphone" in ua:
        system = "iPhone"
    elif "ipad" in ua:
        system = "iPad"
    elif "android" in ua:
        system = "Android"
    elif "mac os" in ua or "macintosh" in ua:
        system = "macOS"
    elif "windows" in ua:
        system = "Windows"
    elif "linux" in ua:
        system = "Linux"
    else:
        system = "Computer"
    if "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    short = (fingerprint or "")[:6] or "local"
    return f"{browser} on {system} · {short}"


def ensure_pool(db: Session) -> None:
    count = db.scalar(select(func.count()).select_from(LicenseKey)) or 0
    existing = {row.code for row in db.scalars(select(LicenseKey)).all()} if count else set()
    while count < POOL_SIZE:
        code = new_code()
        if code in existing:
            continue
        db.add(LicenseKey(id=uuid4(), code=code, status="available"))
        existing.add(code)
        count += 1
    if count:
        db.flush()


def is_licensed(db: Session, user: User, roles: list[str], device_id: str) -> bool:
    if "SUPER_ADMIN" in roles:
        return True
    owned = db.scalar(
        select(LicenseKey.id).where(
            LicenseKey.user_id == user.id,
            LicenseKey.status == "used",
        )
    )
    return owned is not None


def activate_license(db: Session, user: User, roles: list[str], code: str, device_id: str, ip: str = "") -> dict:
    if "SUPER_ADMIN" in roles:
        return {"licensed": True, "status": "not_required"}
    fingerprint = device_fingerprint(device_id)
    if not fingerprint:
        raise LicenseError(400, "This computer could not be identified.")
    if is_licensed(db, user, roles, device_id):
        return {"licensed": True, "status": "already"}
    key = normalize_code(code)
    if not key:
        raise LicenseError(400, "Enter a valid license key.")
    row = db.scalar(select(LicenseKey).where(LicenseKey.code == key).with_for_update())
    if row is None:
        raise LicenseError(400, "That license key is not valid.")
    if row.status == "used":
        if row.device_hash == fingerprint and row.user_id == user.id:
            return {"licensed": True, "status": "already"}
        raise LicenseError(409, "This license is already in use on another computer.")
    row.status = "used"
    row.user_id = user.id
    row.organization_id = user.organization_id
    row.device_hash = fingerprint
    row.bound_at = datetime.now(timezone.utc)
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        actor_type="user",
        action="license.activate",
        entity_type="license_key",
        entity_id=str(row.id),
        after={"code": key, "status": "used"},
        ip_address=ip,
    )
    db.flush()
    return {"licensed": True, "status": "activated"}


def list_licenses(db: Session, roles: list[str]) -> list[dict]:
    if not allows(roles, "users.manage"):
        raise LicenseError(403, "Missing permission")
    ensure_pool(db)
    rows = db.scalars(select(LicenseKey).order_by(LicenseKey.created_at.asc(), LicenseKey.code.asc())).all()
    emails: dict = {}
    user_ids = [row.user_id for row in rows if row.user_id]
    if user_ids:
        emails = {item.id: item.email for item in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "status": row.status,
            "used_by": emails.get(row.user_id, "") if row.user_id else "",
            "bound": bool(row.device_hash),
            "bound_at": row.bound_at.isoformat() if row.bound_at else "",
        }
        for row in rows
    ]
