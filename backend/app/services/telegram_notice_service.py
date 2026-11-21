"""Each login stores its own Telegram API credentials and receives account updates."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.core.encryption import decrypt_json, encrypt_json
from app.models.entities import User, UserTelegramNotice
from app.services.alert_service import TelegramError, _telegram

_CHAT = re.compile(r"^-?\d{5,20}$")
_BOT = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")
logger = logging.getLogger(__name__)


def ensure_notice_table(db: Session) -> None:
    UserTelegramNotice.__table__.create(bind=db.get_bind(), checkfirst=True)


def notice_view(db: Session, user: User) -> dict:
    ensure_notice_table(db)
    row = db.get(UserTelegramNotice, user.id)
    if row is None:
        return {"connected": False, "app_id": "", "chat_id": "", "api_hash_set": False, "bot_token_set": False}
    secret = _secret(row)
    return {
        "connected": bool(row.enabled and secret.get("bot_token") and row.chat_id),
        "app_id": row.app_id,
        "chat_id": row.chat_id,
        "api_hash_set": bool(secret.get("api_hash")),
        "bot_token_set": bool(secret.get("bot_token")),
    }


def save_notice(db: Session, user: User, app_id: str, api_hash: str, bot_token: str, chat_id: str) -> dict:
    ensure_notice_table(db)
    row = db.get(UserTelegramNotice, user.id)
    current = _secret(row) if row is not None else {}
    app_id = app_id.strip() or str(getattr(row, "app_id", "") or "")
    api_hash = api_hash.strip() or str(current.get("api_hash") or "")
    bot_token = bot_token.strip() or str(current.get("bot_token") or "")
    chat_id = chat_id.strip() or str(getattr(row, "chat_id", "") or "")
    if not app_id.isdigit():
        raise TelegramError(400, "Enter the app id from my.telegram.org")
    if len(api_hash) < 8:
        raise TelegramError(400, "Enter the API hash from my.telegram.org")
    if not _BOT.fullmatch(bot_token):
        raise TelegramError(400, "Enter the bot token from BotFather")
    if not _CHAT.fullmatch(chat_id):
        raise TelegramError(400, "Enter the chat id Telegram shows after you message the bot")
    nonce, ciphertext = encrypt_json({"api_hash": api_hash, "bot_token": bot_token})
    if row is None:
        row = UserTelegramNotice(
            user_id=user.id,
            organization_id=user.organization_id,
            app_id=app_id,
            chat_id=chat_id,
            secret_nonce=nonce,
            secret_ciphertext=ciphertext,
            enabled=True,
        )
        db.add(row)
    else:
        row.app_id = app_id
        row.chat_id = chat_id
        row.secret_nonce = nonce
        row.secret_ciphertext = ciphertext
        row.enabled = True
        row.organization_id = user.organization_id
    db.flush()
    return notice_view(db, user)


def send_test(db: Session, user: User) -> dict:
    text = "Maestro is connected. Mining income, contract updates, and account updates will arrive here."
    if not notify_user(db, user.id, text):
        raise TelegramError(400, "Save the Telegram credentials first")
    return {"sent": True}


def notify_user(db: Session, user_id, text: str) -> bool:
    try:
        ensure_notice_table(db)
        row = db.get(UserTelegramNotice, user_id)
        if row is None or not row.enabled or not row.chat_id:
            return False
        token = str(_secret(row).get("bot_token") or "")
        if not _BOT.fullmatch(token):
            return False
        result = _telegram(token, "sendMessage", {"chat_id": row.chat_id, "text": text[:3900]})
        return bool(result.get("ok"))
    except Exception:
        logger.warning("telegram_notice_failed", exc_info=True)
        return False


def _secret(row: UserTelegramNotice | None) -> dict:
    if row is None or not row.secret_nonce or not row.secret_ciphertext:
        return {}
    return decrypt_json(row.secret_nonce, row.secret_ciphertext)
