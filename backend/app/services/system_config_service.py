from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import decrypt_json, encrypt_json
from app.domain.audit import write_audit
from app.models.entities import SystemConfig, User
from app.services.alert_service import telegram_settings
from app.services.email_service import email_status
from app.services.payment_service import provider_status


ACCOUNT_TYPES = (
    ("metaapi", "MetaAPI"),
    ("local_mt5", "MetaTrader 5"),
    ("passprop", "Pass Props"),
    ("pocketoption", "Pocket Option"),
    ("blockchain", "Blockchain contracts"),
    ("mining", "Project Coin"),
    ("webhook", "Webhook"),
)


class SystemConfigError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def merge_account_types(saved: object) -> dict[str, bool]:
    flags = {code: True for code, _label in ACCOUNT_TYPES}
    if isinstance(saved, dict):
        for code in flags:
            if code in saved:
                flags[code] = bool(saved[code])
    return flags


def account_type_flags(db: Session, organization_id: UUID) -> dict[str, bool]:
    return merge_account_types(_read(db, organization_id).get("account_types"))


def account_types_payload(db: Session, organization_id: UUID) -> dict:
    flags = account_type_flags(db, organization_id)
    return {
        "types": [
            {"code": code, "label": label, "enabled": flags[code], "limit": 10 if code in {"local_mt5", "passprop"} else 1}
            for code, label in ACCOUNT_TYPES
        ]
    }


def save_account_types(db: Session, actor: User, enabled: dict, ip: str) -> dict:
    flags = account_type_flags(db, actor.organization_id)
    incoming = enabled if isinstance(enabled, dict) else {}
    unknown = [str(code) for code in incoming if str(code) not in flags]
    if unknown:
        raise SystemConfigError(400, "Unknown account type")
    for code in flags:
        if code in incoming:
            flags[code] = bool(incoming[code])
    secret = _read(db, actor.organization_id)
    secret["account_types"] = flags
    _write(db, actor.organization_id, secret)
    write_audit(
        db,
        organization_id=actor.organization_id,
        actor_user_id=actor.id,
        action="system_account_types_saved",
        entity_type="system_config",
        entity_id=str(actor.organization_id),
        after=flags,
        ip_address=ip,
    )
    return account_types_payload(db, actor.organization_id)


def method_is_open(db: Session, organization_id: UUID, method: str) -> bool:
    return account_type_flags(db, organization_id).get(method, False)


def connector_status(db: Session, organization_id: UUID) -> dict:
    from app.core.encryption import decrypt_json as read_secret
    from app.services.ai_service import openai_api_key
    from app.services.payment_service import _config, _hosted_deposit_credentials

    token = metaapi_token(db, organization_id)
    email = email_status(db, organization_id)
    telegram = telegram_settings(db, organization_id)
    wallet = provider_status(db, organization_id)
    wallet_key = False
    try:
        stored = {}
        row = _config(db, organization_id)
        if row is not None:
            loaded = read_secret(row.secret_nonce, row.secret_ciphertext)
            if isinstance(loaded, dict):
                stored = loaded
        wallet_key = bool(_hosted_deposit_credentials(stored).get("api_key"))
    except Exception:
        wallet_key = False
    openai = bool(openai_api_key(db, organization_id))
    deepseek = False
    from app.models.entities import AiProviderConfig

    ai = db.scalar(select(AiProviderConfig).where(AiProviderConfig.organization_id == organization_id))
    if ai is not None and ai.enabled and ai.provider == "deepseek" and ai.secret_ciphertext:
        from app.services.ai_service import _read_ai_secret

        deepseek = bool(_read_ai_secret(ai).get("api_key"))
    return {
        "metaapi_token_set": len(token) >= 20,
        "wallet_key_set": wallet_key,
        "wallet": wallet,
        "email": email,
        "telegram_bot_set": bool(telegram.get("bot_token_set")),
        "telegram_app_id": str(telegram.get("app_id") or ""),
        "openai_set": openai,
        "deepseek_set": deepseek,
    }


def save_connectors(db: Session, actor: User, payload: dict, ip: str) -> dict:
    token = str(payload.get("metaapi_token") or "").strip()
    if token:
        if len(token) < 20:
            raise SystemConfigError(400, "Paste the MetaAPI token from the MetaAPI dashboard")
        secret = _read(db, actor.organization_id)
        secret["metaapi_token"] = token
        _write(db, actor.organization_id, secret)
        write_audit(
            db,
            organization_id=actor.organization_id,
            actor_user_id=actor.id,
            action="system_metaapi_token_saved",
            entity_type="system_config",
            entity_id=str(actor.organization_id),
            after={"metaapi_token_set": True},
            ip_address=ip,
        )
    wallet = payload.get("wallet")
    if isinstance(wallet, dict) and any(str(wallet.get(key) or "") for key in ("api_key", "ipn_secret", "payout_email", "payout_password")):
        from app.services.payment_service import PaymentError, save_provider

        try:
            save_provider(
                db,
                actor,
                {
                    "provider": "nowpayments",
                    "wallet": "hosted",
                    "sandbox": False,
                    "credentials": {
                        "api_key": str(wallet.get("api_key") or ""),
                        "ipn_secret": str(wallet.get("ipn_secret") or ""),
                        "payout_email": str(wallet.get("payout_email") or ""),
                        "payout_password": wallet.get("payout_password") or "",
                    },
                },
                ip,
            )
        except PaymentError as exc:
            raise SystemConfigError(exc.status, exc.detail) from exc
    return connector_status(db, actor.organization_id)


def metaapi_token(db: Session, organization_id: UUID) -> str:
    saved = str(_read(db, organization_id).get("metaapi_token") or "").strip()
    if len(saved) >= 20:
        return saved
    return get_settings().metaapi_token.strip()


def _row(db: Session, organization_id: UUID) -> SystemConfig:
    row = db.scalar(select(SystemConfig).where(SystemConfig.organization_id == organization_id))
    if row is None:
        row = SystemConfig(id=uuid4(), organization_id=organization_id)
        db.add(row)
        db.flush()
    return row


def _read(db: Session, organization_id: UUID) -> dict:
    row = db.scalar(select(SystemConfig).where(SystemConfig.organization_id == organization_id))
    if row is None or not row.secret_ciphertext:
        return {}
    data = decrypt_json(row.secret_nonce, row.secret_ciphertext)
    return data if isinstance(data, dict) else {}


def _write(db: Session, organization_id: UUID, secret: dict) -> None:
    row = _row(db, organization_id)
    nonce, ciphertext = encrypt_json(secret)
    row.secret_nonce = nonce
    row.secret_ciphertext = ciphertext
    db.flush()
