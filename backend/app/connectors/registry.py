from app.connectors.local_mt5 import LocalMT5Connector
from app.connectors.metaapi import MetaApiConnector
from app.connectors.pocketoption import PocketOptionConnector

_META = MetaApiConnector()
_LOCAL = LocalMT5Connector()
_POCKET = PocketOptionConnector()


def connector_for(method: str):
    if method in {"metaapi", "passprop"}:
        return _META
    if method == "local_mt5":
        return _LOCAL
    if method == "pocketoption":
        return _POCKET
    return None
