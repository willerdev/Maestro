from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import websockets

_DEMO_URLS = (
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
)
_REAL_URLS = (
    "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-us-north.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
)
_HEADERS = {
    "Origin": "https://pocketoption.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def parse_auth_frame(payload: str) -> dict | None:
    text = str(payload or "").strip()
    if not text.startswith("42"):
        return None
    try:
        body = json.loads(text[2:])
    except json.JSONDecodeError:
        return None
    if not isinstance(body, list) or len(body) < 2 or body[0] != "auth" or not isinstance(body[1], dict):
        return None
    data = body[1]
    session = str(data.get("session") or "")
    uid = str(data.get("uid") or "")
    if len(session) < 8 or not uid:
        return None
    return {"wire": text, "is_demo": int(data.get("isDemo") or 0) == 1, "uid": uid}


def parse_balance_frame(payload: str) -> dict | None:
    text = str(payload or "").strip()
    if not text.startswith("42"):
        return None
    try:
        body = json.loads(text[2:])
    except json.JSONDecodeError:
        return None
    if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], dict):
        return None
    if body[0] not in {"balance_data", "balance_updated", "authenticated", "successupdateBalance"}:
        return None
    data = body[1]
    raw = data.get("balance", data.get("demoBalance"))
    if raw in (None, ""):
        return None
    try:
        amount = Decimal(str(raw))
    except Exception:
        return None
    currency = str(data.get("currency") or data.get("currencyCode") or "USD").upper()
    return {"balance": f"{amount:.2f}", "currency": currency[:12]}


class PocketOptionConnector:
    name = "pocketoption"

    def inspect(self, credentials: dict) -> dict:
        uid = str(credentials.get("uid") or "").strip()
        demo_ssid = str(credentials.get("demo_ssid") or "").strip()
        real_ssid = str(credentials.get("real_ssid") or "").strip()
        if not uid or not (demo_ssid or real_ssid):
            return _fail("missing_session", "Sign in through the Pocket Option window first")
        demo = _saved_balance(credentials, "demo")
        real = _saved_balance(credentials, "real")
        try:
            if demo_ssid and demo is None:
                demo = asyncio.run(_read_balance(demo_ssid, True))
            if real_ssid and real is None:
                real = asyncio.run(_read_balance(real_ssid, False))
        except Exception:
            pass
        if demo is None and real is None:
            return _fail("pocketoption_unread", "Pocket Option did not return a demo or real balance")
        parts = []
        if demo:
            parts.append(f"Demo {demo['balance']} {demo['currency']}")
        if real:
            parts.append(f"Real {real['balance']} {real['currency']}")
        currency = (real or demo or {}).get("currency") or "USD"
        shown = (real or demo or {}).get("balance") or "0.00"
        return {
            "ok": True,
            "status": "connected",
            "error_code": "",
            "detail": " · ".join(parts),
            "region": "",
            "account": {
                "display_name": "Pocket Option",
                "account_number": uid,
                "broker": "Pocket Option",
                "server": "demo+real" if demo and real else ("demo" if demo else "real"),
                "currency": currency,
                "leverage": "1",
                "balance": shown,
                "equity": shown,
                "margin": "0",
                "free_margin": shown,
                "margin_level": None,
            },
        }


def _saved_balance(credentials: dict, mode: str) -> dict | None:
    amount = credentials.get(f"{mode}_balance")
    if amount in (None, ""):
        return None
    return {"balance": str(amount), "currency": str(credentials.get(f"{mode}_currency") or "USD")}


async def _read_balance(ssid: str, is_demo: bool) -> dict | None:
    urls = _DEMO_URLS if is_demo else _REAL_URLS
    for url in urls:
        try:
            async with websockets.connect(url, additional_headers=_HEADERS, open_timeout=8, close_timeout=2) as socket:
                await asyncio.wait_for(socket.recv(), 8)
                await socket.send("40")
                sent = False
                for _ in range(12):
                    message = await asyncio.wait_for(socket.recv(), 6)
                    if isinstance(message, bytes):
                        continue
                    if message.startswith("40") and not sent:
                        await socket.send(ssid)
                        sent = True
                        continue
                    if message == "2":
                        await socket.send("3")
                        continue
                    found = parse_balance_frame(message)
                    if found:
                        return found
        except Exception:
            continue
    return None


def _fail(code: str, detail: str) -> dict:
    return {"ok": False, "status": "rejected", "error_code": code, "detail": detail, "region": "", "account": None}
