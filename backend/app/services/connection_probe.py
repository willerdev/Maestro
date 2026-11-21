from __future__ import annotations

from app.connectors.blockchain import BlockchainConnector, MiningConnector
from app.connectors.local_mt5 import LocalMT5Connector
from app.connectors.metaapi import MetaApiConnector
from app.connectors.pocketoption import PocketOptionConnector
from app.core.config import get_settings

METAAPI_METHODS = {"metaapi", "passprop"}


class MetaApiTokenError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


def resolve_metaapi_credentials(credentials: dict | None, *, fallback_token: str = "") -> dict:
    creds = dict(credentials or {})
    source = str(creds.pop("token_source", "") or "").strip().lower()
    own = str(creds.get("token") or "").strip()
    admin = (fallback_token or get_settings().metaapi_token).strip()
    if source == "own" or (source != "default" and len(own) >= 20 and len(admin) < 20):
        return creds
    token = admin if len(admin) >= 20 else own
    if len(token) < 20:
        raise MetaApiTokenError("The default MetaAPI token is not available")
    creds["token"] = token
    return creds


def uses_metaapi(method: str) -> bool:
    return method in METAAPI_METHODS


def probe_connection(method: str, credentials: dict | None, *, metaapi_token: str = "") -> dict:
    payload = credentials or {}
    if uses_metaapi(method):
        try:
            payload = resolve_metaapi_credentials(payload, fallback_token=metaapi_token)
        except MetaApiTokenError as exc:
            return {
                "ok": False,
                "status": "rejected",
                "error_code": "metaapi_token_missing",
                "detail": exc.detail,
                "region": "",
                "account": None,
            }
        return MetaApiConnector().inspect(payload)
    if method == "local_mt5":
        return LocalMT5Connector().inspect(payload)
    if method == "pocketoption":
        return PocketOptionConnector().inspect(payload)
    if method == "blockchain":
        return BlockchainConnector().inspect(payload)
    if method == "mining":
        return MiningConnector().inspect(payload)
    return {
        "ok": False,
        "status": "unsupported",
        "error_code": "unsupported_method",
        "detail": "Choose MetaAPI, MetaTrader 5, Pass Props, Options Trading, contracts, or mining",
        "region": "",
        "account": None,
    }
