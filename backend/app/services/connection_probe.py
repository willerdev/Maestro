from __future__ import annotations

from app.connectors.blockchain import BlockchainConnector, MiningConnector
from app.connectors.local_mt5 import LocalMT5Connector
from app.connectors.metaapi import MetaApiConnector
from app.connectors.pocketoption import PocketOptionConnector
from app.core.config import get_settings


class MetaApiTokenError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


def resolve_metaapi_credentials(credentials: dict | None) -> dict:
    creds = dict(credentials or {})
    source = str(creds.pop("token_source", "") or "").strip().lower()
    if source != "default":
        return creds
    token = get_settings().metaapi_token.strip()
    if len(token) < 20:
        raise MetaApiTokenError("The default MetaAPI token is not available")
    creds["token"] = token
    return creds


def probe_connection(method: str, credentials: dict | None) -> dict:
    payload = credentials or {}
    if method == "metaapi":
        try:
            payload = resolve_metaapi_credentials(payload)
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
        "detail": "Choose MetaAPI, MetaTrader 5, Pocket Option, contracts, or mining",
        "region": "",
        "account": None,
    }
