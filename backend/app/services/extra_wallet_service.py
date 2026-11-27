from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chain.eth import address_from_private, parse_address
from app.core.encryption import EncryptionError, encrypt_json
from app.models.chain_entities import ExtraWalletRow

PROVIDERS = {
    "binance": "Binance Web3 Wallet",
    "bybit": "Bybit Wallet",
    "okx": "OKX Wallet",
}


class ExtraWalletError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def list_extra_wallets(db: Session, org_id: UUID, user_id: UUID) -> list[dict]:
    rows = db.scalars(
        select(ExtraWalletRow).where(
            ExtraWalletRow.organization_id == org_id,
            ExtraWalletRow.user_id == user_id,
        )
    ).all()
    by_id = {row.provider: row for row in rows}
    return [_view(provider, by_id.get(provider)) for provider in PROVIDERS]


def save_extra_wallet(db: Session, org_id: UUID, user_id: UUID, provider: str, payload: dict) -> dict:
    if provider not in PROVIDERS:
        raise ExtraWalletError(400, "Choose Binance, Bybit, or OKX")
    private = str(payload.get("private_key") or "").strip()
    address_in = str(payload.get("address") or "").strip()
    if private:
        try:
            address = address_from_private(private)
        except ValueError as exc:
            raise ExtraWalletError(400, str(exc)) from exc
        try:
            nonce, ciphertext = encrypt_json({"private_key": private.removeprefix("0x").removeprefix("0X").lower(), "provider": provider})
        except EncryptionError as exc:
            raise ExtraWalletError(503, "Wallet encryption is not configured on this server") from exc
        source = "key"
    elif address_in:
        try:
            address = parse_address(address_in)
        except ValueError as exc:
            raise ExtraWalletError(400, str(exc)) from exc
        try:
            nonce, ciphertext = encrypt_json({"address": address, "provider": provider})
        except EncryptionError as exc:
            raise ExtraWalletError(503, "Wallet encryption is not configured on this server") from exc
        source = "address"
    else:
        raise ExtraWalletError(400, "Paste a private key or a public address")
    row = db.scalar(
        select(ExtraWalletRow).where(
            ExtraWalletRow.organization_id == org_id,
            ExtraWalletRow.user_id == user_id,
            ExtraWalletRow.provider == provider,
        )
    )
    if row is None:
        row = ExtraWalletRow(
            organization_id=org_id,
            user_id=user_id,
            provider=provider,
            address=address,
            source=source,
            key_nonce=nonce,
            key_ciphertext=ciphertext,
        )
        db.add(row)
    else:
        row.address = address
        row.source = source
        row.key_nonce = nonce
        row.key_ciphertext = ciphertext
    db.flush()
    return _view(provider, row)


def delete_extra_wallet(db: Session, org_id: UUID, user_id: UUID, provider: str) -> None:
    if provider not in PROVIDERS:
        raise ExtraWalletError(400, "Choose Binance, Bybit, or OKX")
    row = db.scalar(
        select(ExtraWalletRow).where(
            ExtraWalletRow.organization_id == org_id,
            ExtraWalletRow.user_id == user_id,
            ExtraWalletRow.provider == provider,
        )
    )
    if row is not None:
        db.delete(row)


def _view(provider: str, row: ExtraWalletRow | None) -> dict:
    return {
        "id": provider,
        "label": PROVIDERS[provider],
        "address": "" if row is None else row.address,
        "source": "" if row is None else row.source,
        "configured": row is not None,
        "has_key": bool(row is not None and row.source == "key"),
    }
