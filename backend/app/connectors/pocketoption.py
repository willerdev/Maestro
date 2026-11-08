from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import websockets

from app.connectors.types import ConnectionTest, NormalizedAccount, NormalizedPosition

_DEMO_URLS = (
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
)
_REAL_URLS = (
    "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-fr.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-us-north.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-sc.po.market/socket.io/?EIO=4&transport=websocket",
)
_HEADERS = {
    "Origin": "https://pocketoption.com",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
_BALANCE_EVENTS = {
    "authenticated",
    "balanceUpdated",
    "balance_data",
    "balance_updated",
    "successauth",
    "successupdateBalance",
    "updateBalance",
    "updatebalance",
}
_DEAL_EVENTS = {"updateOpenedDeals", "successopenOrder", "updateClosedDeals", "successcloseOrder"}
_ORDER_FAIL = {"failopenOrder", "error", "orders/open/fail"}
_ASSET_ALIASES = {
    "AUCAD": "AUDCAD",
    "AU/CAD": "AUDCAD",
}
_CACHE_TTL = 12.0
_cache: dict[str, tuple[float, dict]] = {}


def pocket_asset(symbol: str) -> str:
    text = str(symbol or "").strip()
    if not text:
        return ""
    compact = re.sub(r"[^A-Za-z0-9]+", "", text).upper()
    otc = compact.endswith("OTC")
    if otc:
        compact = compact[:-3]
    compact = _ASSET_ALIASES.get(compact, compact)
    if not compact:
        return ""
    return f"{compact}_otc" if otc else compact


def binary_order_frame(asset: str, amount, action: str, is_demo: bool, request_id: str, duration: int) -> str:
    qty = int(amount) if float(amount) == int(float(amount)) else float(amount)
    body = {
        "asset": asset,
        "amount": qty,
        "action": action,
        "isDemo": 1 if is_demo else 0,
        "requestId": request_id,
        "optionType": 100,
        "time": int(duration),
    }
    return '42["openOrder",' + json.dumps(body, separators=(",", ":")) + "]"


def _frame(payload: str) -> tuple[str, dict | list] | None:
    text = str(payload or "").strip()
    if not text.startswith("42"):
        return None
    try:
        body = json.loads(text[2:])
    except json.JSONDecodeError:
        return None
    if not isinstance(body, list) or not body:
        return None
    return str(body[0] or ""), body[1] if len(body) > 1 else {}


def parse_auth_frame(payload: str) -> dict | None:
    parsed = _frame(payload)
    if parsed is None:
        return None
    name, data = parsed
    if name not in {"auth", "successauth"} or not isinstance(data, dict):
        return None
    session = str(data.get("session") or "")
    uid = data.get("uid", data.get("id"))
    uid_text = "" if uid in (None, "") else str(uid)
    if name == "auth" and len(session) < 8:
        return None
    if name == "successauth" and not uid_text:
        return None
    demo = data.get("isDemo", data.get("is_demo"))
    platform = data.get("platform", 1)
    try:
        platform_n = int(platform)
    except (TypeError, ValueError):
        platform_n = 1
    return {
        "wire": str(payload).strip() if name == "auth" and len(session) >= 8 else "",
        "is_demo": int(demo or 0) == 1,
        "uid": uid_text,
        "session": session,
        "platform": platform_n or 1,
    }


def parse_balance_frame(payload: str) -> dict | None:
    parsed = _frame(payload)
    if parsed is None:
        return None
    name, data = parsed
    if name not in _BALANCE_EVENTS or not isinstance(data, dict):
        return None
    return _money_fields(data)


def parse_session_payload(data: object) -> dict | None:
    """Read balance/uid from a Pocket Option JSON blob, including binary Socket.IO attachments."""
    if isinstance(data, list):
        for item in data:
            found = parse_session_payload(item)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None
    found = _money_fields(data)
    if found:
        return found
    for key in ("data", "msg", "message", "result", "payload"):
        nested = data.get(key)
        if nested is not None and nested is not data:
            found = parse_session_payload(nested)
            if found:
                return found
    return None


def format_ssid(wire: str, is_demo: bool, uid: str = "") -> str:
    text = str(wire or "").strip()
    parsed = parse_auth_frame(text) if text.startswith("42") else None
    session = str((parsed or {}).get("session") or "")
    uid_text = str((parsed or {}).get("uid") or uid or "")
    platform = int((parsed or {}).get("platform") or 1)
    if parsed and session and bool(parsed.get("is_demo")) == bool(is_demo):
        return parsed.get("wire") or text
    if not session:
        if text.startswith("42") or len(text) < 8:
            return ""
        session = text
    body = {"session": session, "isDemo": 1 if is_demo else 0, "uid": int(uid_text) if uid_text.isdigit() else 0, "platform": platform or 1}
    return '42["auth",' + json.dumps(body, separators=(",", ":")) + "]"


def read_session(ssid: str, is_demo: bool, uid: str = "", url: str = "") -> dict | None:
    wire = format_ssid(ssid, is_demo, uid)
    if not wire:
        return None
    key = f"{int(is_demo)}:{hash(wire)}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    found = _run(_connect_and_read(wire, is_demo, url), timeout=28)
    if found:
        _cache[key] = (now, found)
    return found


class PocketOptionConnector:
    name = "pocketoption"

    def inspect(self, credentials: dict) -> dict:
        uid = str(credentials.get("uid") or "").strip()
        demo_ssid = str(credentials.get("demo_ssid") or "").strip()
        real_ssid = str(credentials.get("real_ssid") or "").strip()
        if not uid and not (demo_ssid or real_ssid):
            return _fail("missing_session", "Sign in through the Pocket Option window first")
        demo = _side_state(credentials, "demo", uid, placeholder=True)
        real = _side_state(credentials, "real", uid, placeholder=True)
        uid = str((real or demo or {}).get("uid") or uid or "").strip()
        if not uid or not (demo or real):
            return _fail("missing_session", "Sign in through the Pocket Option window first")
        mode = _active_mode(credentials, bool(real), bool(demo))
        shown = (demo if mode == "demo" else real) or real or demo or {}
        parts = []
        if demo:
            parts.append(f"Demo {demo['balance']} {demo['currency']}")
        if real:
            parts.append(f"Real {real['balance']} {real['currency']}")
        return {
            "ok": True,
            "status": "connected",
            "error_code": "",
            "detail": " · ".join(parts) or f"Signed in · {uid}",
            "region": str(shown.get("ws_url") or ""),
            "demo": demo,
            "real": real,
            "account": {
                "display_name": "Pocket Option",
                "account_number": uid,
                "broker": "Pocket Option",
                "server": mode,
                "currency": shown.get("currency") or "USD",
                "leverage": "1",
                "balance": shown.get("balance") or "0.00",
                "equity": shown.get("equity") or shown.get("balance") or "0.00",
                "margin": "0",
                "free_margin": shown.get("balance") or "0.00",
                "margin_level": None,
            },
        }

    def test_connection(self, credentials: dict) -> ConnectionTest:
        result = self.inspect(credentials)
        return ConnectionTest(result["ok"], result["status"], result.get("error_code") or "", result.get("detail") or "")

    def fetch_account(self, credentials: dict) -> NormalizedAccount:
        live = _preferred_live(credentials)
        if live is None:
            raise RuntimeError("Pocket Option did not return a live balance")
        balance = Decimal(live["balance"])
        equity = Decimal(live.get("equity") or live["balance"])
        return NormalizedAccount(balance=balance, equity=equity, margin=Decimal("0"), free_margin=balance, margin_level=None, currency=live.get("currency") or "USD")

    def fetch_positions(self, credentials: dict) -> list[NormalizedPosition]:
        live = _preferred_live(credentials)
        if live is None:
            raise RuntimeError("Pocket Option did not return open trades")
        rows: list[NormalizedPosition] = []
        for deal in live.get("deals") or []:
            if not isinstance(deal, dict):
                continue
            ticket = str(deal.get("id") or deal.get("ticket") or "").strip()
            symbol = str(deal.get("asset") or deal.get("symbol") or "").strip()
            if not ticket or not symbol:
                continue
            amount = _dec(deal.get("amount"), "0")
            price = _dec(deal.get("openPrice", deal.get("open_price", deal.get("price"))), "0")
            current = _quote(deal, price)
            profit = _dec(deal.get("profit", deal.get("profitAmount")), "0")
            command = deal.get("command", deal.get("action", deal.get("direction")))
            side = "buy" if str(command).lower() in {"0", "call", "buy"} else "sell"
            if profit == 0 and current != price:
                profit = current - price if side == "buy" else price - current
            rows.append(
                NormalizedPosition(
                    account_id=None,
                    ticket=ticket,
                    symbol=symbol,
                    side=side,
                    volume=amount,
                    entry_price=price,
                    current_price=current,
                    stop_loss=None,
                    take_profit=None,
                    profit=profit,
                    swap=Decimal("0"),
                    commission=Decimal("0"),
                    open_time=_deal_time(deal),
                    magic_number=0,
                    comment="",
                )
            )
        return rows

    def open_binary(self, credentials: dict, *, symbol: str, side: str, amount, duration: int) -> dict:
        asset = pocket_asset(symbol)
        if not asset:
            return {"ok": False, "message": "Enter an asset"}
        action = "put" if str(side).lower() in {"sell", "put", "short"} else "call"
        uid = str(credentials.get("uid") or "")
        has_real = bool(str(credentials.get("real_ssid") or credentials.get("demo_ssid") or "").strip())
        has_demo = bool(str(credentials.get("demo_ssid") or credentials.get("real_ssid") or "").strip())
        is_demo = _active_mode(credentials, has_real, has_demo) == "demo"
        ssid = format_ssid(_session_wire(credentials, is_demo), is_demo, uid)
        if not ssid:
            return {"ok": False, "message": "Sign in through the Pocket Option window first"}
        try:
            qty = Decimal(str(amount))
        except Exception:
            return {"ok": False, "message": "Enter a stake"}
        found = _run(_connect_and_place(ssid, is_demo, asset, qty, action, int(duration), _mode_url(credentials, is_demo)), timeout=20)
        if not found:
            return {"ok": False, "message": "Pocket Option did not take the trade"}
        return found


def _side_state(credentials: dict, mode: str, uid: str, *, placeholder: bool = False) -> dict | None:
    is_demo = mode == "demo"
    ssid = _session_wire(credentials, is_demo)
    if not ssid:
        return None
    live = read_session(ssid, is_demo, uid, _mode_url(credentials, is_demo))
    if live and _book_matches(live, is_demo):
        live["uid"] = str(live.get("uid") or uid)
        return live
    saved = _saved_balance(credentials, mode)
    if saved:
        saved["uid"] = uid
        return saved
    if placeholder:
        return {"balance": "0.00", "currency": str(credentials.get(f"{mode}_currency") or "USD"), "uid": uid, "deals": []}
    return None


def _active_mode(credentials: dict, has_real: bool, has_demo: bool) -> str:
    mode = str(credentials.get("active_mode") or "").strip().lower()
    if mode == "demo" and has_demo:
        return "demo"
    if mode == "real" and has_real:
        return "real"
    if has_real:
        return "real"
    return "demo"


def _session_wire(credentials: dict, is_demo: bool) -> str:
    preferred = "demo" if is_demo else "real"
    other = "real" if is_demo else "demo"
    return str(credentials.get(f"{preferred}_ssid") or credentials.get(f"{other}_ssid") or "").strip()


def _mode_url(credentials: dict, is_demo: bool) -> str:
    preferred = "demo_ws_url" if is_demo else "real_ws_url"
    for key in (preferred, "ws_url"):
        url = str(credentials.get(key) or "")
        if url.startswith("wss://") and _url_matches(url, is_demo):
            return url
    return ""


def _url_matches(url: str, is_demo: bool) -> bool:
    demo_host = "demo" in url or "try-demo" in url
    return demo_host if is_demo else not demo_host


def _book_matches(live: dict, is_demo: bool) -> bool:
    if "is_demo" not in live:
        return True
    return bool(live.get("is_demo")) == bool(is_demo)


def _preferred_live(credentials: dict) -> dict | None:
    uid = str(credentials.get("uid") or "")
    has_real = bool(str(credentials.get("real_ssid") or credentials.get("demo_ssid") or "").strip())
    has_demo = bool(str(credentials.get("demo_ssid") or credentials.get("real_ssid") or "").strip())
    preferred = _active_mode(credentials, has_real, has_demo)
    is_demo = preferred == "demo"
    ssid = _session_wire(credentials, is_demo)
    if not ssid:
        return None
    live = read_session(ssid, is_demo, uid, _mode_url(credentials, is_demo))
    if live and _book_matches(live, is_demo):
        live["uid"] = str(live.get("uid") or uid)
        return live
    saved = _saved_balance(credentials, preferred)
    if saved:
        saved["uid"] = uid
        return saved
    return None


def _saved_balance(credentials: dict, mode: str) -> dict | None:
    amount = credentials.get(f"{mode}_balance")
    if amount in (None, "", "—", "-"):
        return None
    try:
        value = Decimal(str(amount))
    except Exception:
        return None
    return {"balance": f"{value:.2f}", "currency": str(credentials.get(f"{mode}_currency") or "USD"), "deals": []}


def _money_fields(data: dict) -> dict | None:
    raw = data.get("balance", data.get("demoBalance"))
    if raw in (None, "", "—", "-"):
        return None
    try:
        amount = Decimal(str(raw))
    except Exception:
        return None
    currency = str(data.get("currency") or data.get("currencyCode") or "USD").upper()
    uid = data.get("uid", data.get("id"))
    demo = data.get("isDemo", data.get("is_demo"))
    found = {"balance": f"{amount:.2f}", "currency": (currency or "USD")[:12]}
    if uid not in (None, ""):
        found["uid"] = str(uid)
    if demo is not None:
        found["is_demo"] = int(demo) == 1
    return found


def _collect_deals(data: object, rows: list[dict]) -> None:
    if isinstance(data, dict):
        deals = data.get("deals")
        if isinstance(deals, list):
            rows.extend(item for item in deals if isinstance(item, dict))
        if data.get("asset") and data.get("amount") is not None and data.get("id"):
            rows.append(data)
        return
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _collect_deals(item, rows)


async def _connect_and_read(ssid: str, is_demo: bool, preferred_url: str = "") -> dict | None:
    urls = list(_DEMO_URLS if is_demo else _REAL_URLS)
    if preferred_url.startswith("wss://") and _url_matches(preferred_url, is_demo):
        urls = [preferred_url, *[item for item in urls if item != preferred_url]]
    for url in urls[:4]:
        found = await _read_one(url, ssid)
        if found:
            found["ws_url"] = url
            return found
    return None


async def _connect_and_place(ssid: str, is_demo: bool, asset: str, amount: Decimal, action: str, duration: int, preferred_url: str = "") -> dict | None:
    urls = list(_DEMO_URLS if is_demo else _REAL_URLS)
    if preferred_url.startswith("wss://") and _url_matches(preferred_url, is_demo):
        urls = [preferred_url, *[item for item in urls if item != preferred_url]]
    last: dict | None = None
    for url in urls[:4]:
        found = await _place_one(url, ssid, is_demo, asset, amount, action, duration)
        if found and found.get("ok"):
            return found
        if found:
            last = found
    return last


async def _place_one(url: str, ssid: str, is_demo: bool, asset: str, amount: Decimal, action: str, duration: int) -> dict | None:
    request_id = uuid.uuid4().hex
    pending: list | None = None
    authenticated = False
    sent = False
    result: dict | None = None
    try:
        async with websockets.connect(url, additional_headers=_HEADERS, open_timeout=8, close_timeout=2, ping_interval=None, max_size=8_000_000) as socket:
            opening = await asyncio.wait_for(socket.recv(), 8)
            if isinstance(opening, bytes):
                opening = opening.decode("utf-8", "replace")
            if not str(opening).startswith("0") or "sid" not in str(opening):
                return None
            await socket.send("40")
            namespace = await asyncio.wait_for(socket.recv(), 8)
            if isinstance(namespace, bytes):
                namespace = namespace.decode("utf-8", "replace")
            if not str(namespace).startswith("40"):
                return None
            await socket.send(ssid)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                try:
                    message = await asyncio.wait_for(socket.recv(), remaining)
                except (asyncio.TimeoutError, TimeoutError):
                    break
                if message == "2" or message == b"2":
                    await socket.send("3")
                    continue
                text, blob = _decode_message(message)
                if text == "41" or (text and "NotAuthorized" in text):
                    return {"ok": False, "message": "Pocket Option rejected the session"}
                event_name = ""
                event_body: object = blob
                if text and text.startswith("451-"):
                    try:
                        pending = json.loads(text.split("-", 1)[1])
                    except json.JSONDecodeError:
                        pending = None
                    continue
                if blob is not None:
                    if parse_session_payload(blob):
                        authenticated = True
                    if pending and isinstance(pending, list) and pending:
                        event_name = str(pending[0] or "")
                        event_body = blob
                        pending = None
                    elif isinstance(blob, list) and blob:
                        event_name = str(blob[0] or "")
                        event_body = blob[1] if len(blob) > 1 else blob
                elif text and text.startswith("42"):
                    parsed = _frame(text)
                    if parsed is None:
                        continue
                    event_name, event_body = parsed
                if event_name in {"successauth", "authenticated"}:
                    authenticated = True
                if authenticated and not sent:
                    await socket.send(binary_order_frame(asset, amount, action, is_demo, request_id, duration))
                    sent = True
                order = _order_result(event_name, event_body, request_id, asset, amount, action)
                if order:
                    result = order
                    if order.get("ok") or order.get("final"):
                        return order
    except Exception:
        return result
    return result


def _order_result(event_name: str, data: object, request_id: str, asset: str, amount: Decimal, action: str) -> dict | None:
    if event_name in _ORDER_FAIL:
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("message") or data.get("error") or data.get("msg") or "")
        return {"ok": False, "final": True, "message": detail or "Pocket Option rejected the trade"}
    if event_name not in {"successopenOrder", "updateOpenedDeals"}:
        return None
    rows: list[dict] = []
    _collect_deals(data, rows)
    if isinstance(data, dict):
        rows.append(data)
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticket = str(row.get("id") or row.get("ticket") or row.get("orderId") or "").strip()
        req = str(row.get("requestId") or row.get("request_id") or "")
        if req and req != request_id:
            continue
        if event_name == "updateOpenedDeals" and req != request_id:
            continue
        if not ticket and not req:
            continue
        return {
            "ok": True,
            "ticket": ticket or request_id,
            "asset": str(row.get("asset") or asset),
            "price": str(row.get("openPrice") or row.get("open_price") or row.get("price") or "0"),
            "amount": str(row.get("amount") or amount),
            "action": action,
            "message": "Trade opened",
        }
    return None


async def _read_one(url: str, ssid: str) -> dict | None:
    pending: list | None = None
    authenticated = False
    found: dict | None = None
    deals: list[dict] = []
    try:
        async with websockets.connect(url, additional_headers=_HEADERS, open_timeout=8, close_timeout=2, ping_interval=None, max_size=8_000_000) as socket:
            opening = await asyncio.wait_for(socket.recv(), 8)
            if isinstance(opening, bytes):
                opening = opening.decode("utf-8", "replace")
            if not str(opening).startswith("0") or "sid" not in str(opening):
                return None
            await socket.send("40")
            namespace = await asyncio.wait_for(socket.recv(), 8)
            if isinstance(namespace, bytes):
                namespace = namespace.decode("utf-8", "replace")
            if not str(namespace).startswith("40"):
                return None
            await socket.send(ssid)
            await socket.send('42["ps"]')
            await socket.send('42["getBalance"]')
            deadline = time.monotonic() + 8
            asked = True
            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                try:
                    message = await asyncio.wait_for(socket.recv(), remaining)
                except (asyncio.TimeoutError, TimeoutError):
                    break
                if message == "2" or message == b"2":
                    await socket.send("3")
                    continue
                text, blob = _decode_message(message)
                if text == "41" or (text and "NotAuthorized" in text):
                    return None
                if text and text.startswith("451-"):
                    try:
                        pending = json.loads(text.split("-", 1)[1])
                    except json.JSONDecodeError:
                        pending = None
                    continue
                if blob is not None:
                    money = parse_session_payload(blob)
                    if money:
                        found = {**(found or {}), **money}
                    event_name = ""
                    event_body: object = blob
                    if pending and isinstance(pending, list) and pending:
                        event_name = str(pending[0] or "")
                        pending = None
                    elif isinstance(blob, list) and blob:
                        event_name = str(blob[0] or "")
                        event_body = blob[1] if len(blob) > 1 else blob
                    if event_name in {"successauth", "authenticated"}:
                        authenticated = True
                    if event_name in _DEAL_EVENTS or (isinstance(event_body, dict) and "deals" in event_body):
                        _collect_deals(event_body, deals)
                    elif isinstance(blob, dict):
                        _collect_deals(blob, deals)
                    continue
                if text and text.startswith("42"):
                    parsed = _frame(text)
                    if parsed is None:
                        continue
                    name, data = parsed
                    if name in {"successauth", "authenticated"}:
                        authenticated = True
                    money = parse_session_payload(data) if isinstance(data, dict) else None
                    if money:
                        found = {**(found or {}), **money}
                    if name in _DEAL_EVENTS:
                        _collect_deals(data, deals)
                if authenticated and not asked:
                    await socket.send('42["ps"]')
                    await socket.send('42["getBalance"]')
                    asked = True
                if found and authenticated:
                    break
    except Exception:
        return None
    if not found:
        return None
    found["deals"] = deals
    found["equity"] = found.get("balance")
    return found


def _decode_message(message: object) -> tuple[str, object | None]:
    if isinstance(message, bytes):
        text = message.decode("utf-8", "replace")
        try:
            return text, json.loads(text)
        except json.JSONDecodeError:
            return text, None
    text = str(message or "")
    return text, None


def _run(coro, timeout: float = 28):
    def go():
        return asyncio.run(coro)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return go()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(go).result(timeout=timeout)


def _quote(deal: dict, fallback: Decimal) -> Decimal:
    for key in ("currentPrice", "currentQuote", "closePrice", "close_price", "quote", "priceCurrent"):
        if deal.get(key) not in (None, ""):
            return _dec(deal.get(key), str(fallback))
    return fallback


def _dec(value: object, default: str) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except Exception:
        return Decimal(default)


def _deal_time(deal: dict) -> datetime | None:
    raw = deal.get("openTimestamp", deal.get("openTime", deal.get("time")))
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)):
        stamp = float(raw)
        if stamp > 1_000_000_000_000:
            stamp /= 1000
        return datetime.fromtimestamp(stamp, tz=timezone.utc)
    text = str(raw).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _fail(code: str, detail: str) -> dict:
    return {"ok": False, "status": "rejected", "error_code": code, "detail": detail, "region": "", "account": None}
