from __future__ import annotations

import asyncio
import base64
import json
import shutil
import socket
import subprocess
import threading
import uuid
from pathlib import Path

import httpx
import websockets

from app.connectors.options_platforms import BROWSER_SESSION, normalize_platform, platform_label, platform_row
from app.connectors.pocketoption import format_ssid, parse_auth_frame, parse_balance_frame, parse_session_payload, read_session

_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_ROOT = Path(__file__).resolve().parents[4] / ".runtime" / "pocket-chrome"
_LOCK = threading.Lock()
_SESSIONS: dict[str, "PocketLogin"] = {}
_PAGE_STATE = """
(() => {
  const url = String(location.href || "");
  const path = String(location.pathname || "").toLowerCase();
  const loginish = /login|sign-in|signin|sign_in|oauth|register|signup|authorization/.test(path + " " + url);
  let uid = "";
  try {
    let ls = "";
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      ls += key + "=" + String(localStorage.getItem(key) || "") + "|";
    }
    const match = ls.match(/loginid["']?\\s*[:=]\\s*["']?([A-Za-z0-9_-]+)/i)
      || ls.match(/user_id["']?\\s*[:=]\\s*["']?(\\d+)/i)
      || ls.match(/uid["']?\\s*[:=]\\s*["']?(\\d+)/i);
    if (match) uid = match[1];
  } catch (err) {}
  const text = document.body ? String(document.body.innerText || "").slice(0, 4000) : "";
  const money = text.match(/(?:USD|EUR|USDT|\\$|€)\\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\\.[0-9]{2})?)/)
    || text.match(/([0-9]{1,3}(?:,[0-9]{3})*(?:\\.[0-9]{2})?)\\s*(?:USD|EUR|USDT)/);
  const balance = money ? String(money[1] || "").replace(/,/g, "") : "";
  return { url, loginish, uid, balance, cookieLen: String(document.cookie || "").length };
})()
"""


class PocketLoginError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


class PocketLogin:
    def __init__(self, session_id: str, user_id: str, preferred_mode: str = "real", platform: str = "pocketoption") -> None:
        self.id = session_id
        self.user_id = user_id
        self.platform = platform
        self.label = platform_label(platform)
        self.config = platform_row(platform)
        self.preferred_mode = preferred_mode if preferred_mode in {"demo", "real"} else "real"
        self.port = _free_port()
        self.profile = _ROOT / session_id
        self.process: subprocess.Popen | None = None
        self.closed = False
        self.error = ""
        self.uid = ""
        self.demo_ssid = ""
        self.real_ssid = ""
        self.demo_balance = ""
        self.demo_currency = "USD"
        self.real_balance = ""
        self.real_currency = "USD"
        self.session_ok = False
        self.cookies: list[dict] = []
        self._mode = ""
        self._pending_balance: dict | None = None
        self._live_done = {"demo": False, "real": False}
        self._live_busy = {"demo": False, "real": False}

    def start(self) -> None:
        if not Path(_CHROME).exists():
            raise PocketLoginError(f"Google Chrome is not installed, so the {self.label} window cannot open")
        self.profile.mkdir(parents=True, exist_ok=True)
        (self.profile / "First Run").touch()
        self.process = subprocess.Popen(
            [
                _CHROME,
                f"--remote-debugging-port={self.port}",
                "--remote-debugging-address=127.0.0.1",
                f"--user-data-dir={self.profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-allow-origins=*",
                "--disable-sync",
                "--disable-background-networking",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        threading.Thread(target=self._watch, name=f"pocket-{self.id[:8]}", daemon=True).start()

    def snapshot(self) -> dict:
        self._kick_live()
        return self._snapshot_body()

    def _snapshot_body(self) -> dict:
        demo = self._book("demo")
        real = self._book("real")
        preferred = demo if self.preferred_mode == "demo" else real
        ready = bool(preferred and preferred.get("balance") not in (None, "", "—"))
        if self.platform != "pocketoption" and self.session_ok:
            ready = True
            if not preferred or preferred.get("balance") in (None, "", "—"):
                self._mode = self.preferred_mode
                self._apply_balance({"balance": "0.00", "currency": "USD"})
                demo = self._book("demo")
                real = self._book("real")
                preferred = demo if self.preferred_mode == "demo" else real
        book = "Demo" if self.preferred_mode == "demo" else "Real"
        if self.error:
            detail = self.error
        elif ready:
            detail = f"{book} {preferred['balance']} {preferred.get('currency') or 'USD'}"
            other = real if self.preferred_mode == "demo" else demo
            if other and other.get("balance") not in (None, "", "—"):
                other_name = "Real" if self.preferred_mode == "demo" else "Demo"
                detail = f"{detail} · {other_name} {other['balance']} {other.get('currency') or 'USD'}"
        elif self.demo_ssid or self.real_ssid:
            detail = f"Signed in. Reading the {book} book…"
        else:
            detail = f"Sign in on {book} in the {self.label} window. That book is read first. You can switch after."
        return {
            "id": self.id,
            "status": "failed" if self.error else ("captured" if ready else "waiting"),
            "detail": detail,
            "uid": self.uid,
            "preferred_mode": self.preferred_mode,
            "platform": self.platform,
            "platform_label": self.label,
            "demo": demo,
            "real": real,
        }

    def _book(self, mode: str) -> dict | None:
        ssid = self.demo_ssid if mode == "demo" else self.real_ssid
        balance = self.demo_balance if mode == "demo" else self.real_balance
        currency = self.demo_currency if mode == "demo" else self.real_currency
        other = self.real_ssid if mode == "demo" else self.demo_ssid
        if self.platform != "pocketoption" and self.session_ok and self.preferred_mode == mode:
            return {"uid": self.uid, "balance": balance or "0.00", "currency": currency or "USD"}
        if not ssid and not balance and not (self.preferred_mode == mode and other):
            return None
        return {"uid": self.uid, "balance": balance or "—", "currency": currency or "USD"}

    def credentials(self) -> dict:
        if self.platform != "pocketoption":
            if not self.session_ok:
                raise PocketLoginError(f"Sign in inside the {self.label} window first")
            uid = self.uid or f"{self.platform}-{self.id[:10]}"
            mode = self.preferred_mode
            return {
                "options_platform": self.platform,
                "uid": uid,
                "active_mode": mode,
                "session_ok": True,
                "cookies": self.cookies,
                "demo_ssid": BROWSER_SESSION if mode == "demo" or self.demo_ssid else "",
                "real_ssid": BROWSER_SESSION if mode == "real" or self.real_ssid else "",
                "demo_balance": self.demo_balance,
                "demo_currency": self.demo_currency,
                "real_balance": self.real_balance,
                "real_currency": self.real_currency,
            }
        if not self.uid or not (self.demo_ssid or self.real_ssid):
            raise PocketLoginError(f"Sign in inside the {self.label} window first")
        demo_ssid = self.demo_ssid or (format_ssid(self.real_ssid, True, self.uid) if self.preferred_mode == "demo" else "")
        real_ssid = self.real_ssid or (format_ssid(self.demo_ssid, False, self.uid) if self.preferred_mode == "real" else "")
        return {
            "options_platform": self.platform,
            "uid": self.uid,
            "active_mode": self.preferred_mode,
            "demo_ssid": demo_ssid,
            "real_ssid": real_ssid,
            "demo_balance": self.demo_balance,
            "demo_currency": self.demo_currency,
            "real_balance": self.real_balance,
            "real_currency": self.real_currency,
        }

    def close(self) -> None:
        self.closed = True
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def _watch(self) -> None:
        try:
            asyncio.run(self._collect())
        except Exception:
            if not self.closed:
                self.error = f"The {self.label} window stopped before a session was captured"

    async def _collect(self) -> None:
        seen: set[str] = set()
        opened = False
        for _ in range(300):
            if self.closed:
                return
            try:
                response = httpx.get(f"http://127.0.0.1:{self.port}/json", timeout=2)
                targets = response.json()
            except Exception:
                await asyncio.sleep(0.4)
                continue
            if not opened:
                await self._open_login_target(targets)
                opened = True
                continue
            for target in targets:
                address = str(target.get("webSocketDebuggerUrl") or "")
                kind = str(target.get("type") or "")
                url = str(target.get("url") or "")
                if not address or address in seen:
                    continue
                if kind in {"background_page", "service_worker", "worker", "browser"}:
                    continue
                if url.startswith("chrome-extension://") or url.startswith("chrome://"):
                    continue
                if kind not in {"page", "webview", "other", "tab"}:
                    continue
                seen.add(address)
                asyncio.create_task(self._attach(address))
            await asyncio.sleep(1)

    async def _open_login_target(self, targets: list) -> None:
        login = str(self.config["login_url"])
        pages = [
            row
            for row in (targets or [])
            if str(row.get("type") or "") in {"page", "webview", "other", "tab"}
            and str(row.get("webSocketDebuggerUrl") or "")
            and not str(row.get("url") or "").startswith(("chrome-extension://", "chrome://"))
        ]
        if pages:
            address = str(pages[0].get("webSocketDebuggerUrl") or "")
            if address:
                await self._navigate_target(address, login)
            return
        try:
            version = httpx.get(f"http://127.0.0.1:{self.port}/json/version", timeout=2).json()
            browser_ws = str(version.get("webSocketDebuggerUrl") or "")
        except Exception:
            return
        if not browser_ws:
            return
        try:
            async with websockets.connect(browser_ws, open_timeout=5, max_size=8_000_000) as socket:
                await socket.send(json.dumps({"id": 1, "method": "Target.setDiscoverTargets", "params": {"discover": True}}))
                await socket.send(
                    json.dumps(
                        {
                            "id": 2,
                            "method": "Target.createTarget",
                            "params": {"url": login, "newWindow": True},
                        }
                    )
                )
                await asyncio.wait_for(socket.recv(), 8)
        except Exception:
            return

    async def _navigate_target(self, address: str, url: str) -> None:
        try:
            async with websockets.connect(address, open_timeout=5, max_size=8_000_000) as socket:
                await socket.send(json.dumps({"id": 1, "method": "Page.enable"}))
                await socket.send(json.dumps({"id": 2, "method": "Page.navigate", "params": {"url": url}}))
                await asyncio.wait_for(socket.recv(), 5)
        except Exception:
            return

    async def _attach(self, address: str) -> None:
        cmd = 0
        steered = False
        eval_ids: set[int] = set()
        cookie_ids: set[int] = set()

        async def send(method: str, params: dict | None = None) -> int:
            nonlocal cmd
            cmd += 1
            await socket.send(json.dumps({"id": cmd, "method": method, "params": params or {}}))
            return cmd

        try:
            async with websockets.connect(address, open_timeout=5, max_size=8_000_000) as socket:
                await send("Network.enable")
                await send("Page.enable")
                if self.platform != "pocketoption":
                    await send("Runtime.enable")

                async def ping_page() -> None:
                    while not self.closed:
                        eval_ids.add(await send("Runtime.evaluate", {"expression": _PAGE_STATE, "returnByValue": True}))
                        cookie_ids.add(await send("Network.getAllCookies"))
                        await asyncio.sleep(1.5)

                pinger = asyncio.create_task(ping_page()) if self.platform != "pocketoption" else None
                try:
                    while not self.closed:
                        raw = await asyncio.wait_for(socket.recv(), 30)
                        message = json.loads(raw)
                        params = message.get("params") or {}
                        mid = message.get("id")
                        if mid in eval_ids:
                            eval_ids.discard(mid)
                            value = ((message.get("result") or {}).get("result") or {}).get("value")
                            self._note_page(value)
                            if not steered and self.session_ok:
                                steered = True
                                await send("Page.navigate", {"url": self._cabinet_url()})
                            continue
                        if mid in cookie_ids:
                            cookie_ids.discard(mid)
                            rows = (message.get("result") or {}).get("cookies") or []
                            if isinstance(rows, list) and rows:
                                self.cookies = [row for row in rows if isinstance(row, dict)][:80]
                            continue
                        payload = ""
                        if message.get("method") in {"Network.webSocketFrameSent", "Network.webSocketFrameReceived"}:
                            frame = params.get("response") or {}
                            payload = str(frame.get("payloadData") or "")
                            if frame.get("opcode") == 2 and payload:
                                try:
                                    payload = base64.b64decode(payload).decode("utf-8", "replace")
                                except Exception:
                                    payload = ""
                        if self.platform == "pocketoption":
                            self._note(payload)
                            if not steered and self._should_steer():
                                steered = True
                                await send("Page.navigate", {"url": self._cabinet_url()})
                finally:
                    if pinger is not None:
                        pinger.cancel()
        except Exception:
            return

    def _cabinet_url(self) -> str:
        key = "demo_url" if self.preferred_mode == "demo" else "real_url"
        return str(self.config.get(key) or self.config["login_url"])

    def _should_steer(self) -> bool:
        if self.preferred_mode == "demo":
            return bool(self.uid or self.real_ssid) and not self.demo_ssid
        return bool(self.uid or self.demo_ssid) and not self.real_ssid

    def _note(self, payload: str) -> None:
        auth = parse_auth_frame(payload)
        if auth:
            if auth["uid"]:
                self.uid = auth["uid"]
            self._mode = "demo" if auth["is_demo"] else "real"
            if auth["wire"]:
                if auth["is_demo"]:
                    self.demo_ssid = auth["wire"]
                else:
                    self.real_ssid = auth["wire"]
            money = parse_balance_frame(payload)
            if money:
                self._apply_balance(money)
            elif self._pending_balance:
                pending_demo = self._pending_balance.get("is_demo")
                if pending_demo is not None and bool(pending_demo) == auth["is_demo"]:
                    self._apply_balance(self._pending_balance)
                self._pending_balance = None
            return
        found = parse_balance_frame(payload) or _blob_balance(payload)
        if not found:
            return
        if found.get("is_demo") is True:
            self._mode = "demo"
        elif found.get("is_demo") is False:
            self._mode = "real"
        if found.get("uid") and not self.uid:
            self.uid = str(found["uid"])
        if not self._mode:
            self._pending_balance = found
            return
        tagged = found.get("is_demo")
        if tagged is not None and ((tagged is True) != (self._mode == "demo")):
            return
        self._apply_balance(found)

    def _apply_balance(self, found: dict) -> None:
        if found.get("uid"):
            self.uid = str(found["uid"])
        if self._mode == "demo":
            self.demo_balance = found["balance"]
            self.demo_currency = found["currency"]
        else:
            self.real_balance = found["balance"]
            self.real_currency = found["currency"]

    def _note_page(self, value: object) -> None:
        if not isinstance(value, dict):
            return
        if value.get("uid") and not self.uid:
            self.uid = str(value["uid"])
        balance = str(value.get("balance") or "").strip()
        if balance and balance.replace(".", "", 1).isdigit():
            self._mode = self.preferred_mode
            self._apply_balance({"balance": f"{float(balance):.2f}", "currency": "USD"})
        loginish = bool(value.get("loginish"))
        cookie_len = int(value.get("cookieLen") or 0)
        url = str(value.get("url") or "")
        hosts = tuple(str(item) for item in self.config.get("hosts") or ())
        on_site = any(host in url for host in hosts) if hosts else True
        if on_site and not loginish and (cookie_len > 10 or self.uid or self.demo_balance or self.real_balance):
            self.session_ok = True
            token = BROWSER_SESSION
            if self.preferred_mode == "demo":
                self.demo_ssid = self.demo_ssid or token
            else:
                self.real_ssid = self.real_ssid or token
            if not self.uid:
                self.uid = f"{self.platform}-{self.id[:10]}"

    def _kick_live(self) -> None:
        if self.platform != "pocketoption":
            return
        either = self.real_ssid or self.demo_ssid
        if not either:
            return
        preferred = self.preferred_mode
        other = "real" if preferred == "demo" else "demo"
        preferred_ready = bool(self.demo_balance if preferred == "demo" else self.real_balance)
        if not preferred_ready:
            if not self._live_busy[preferred]:
                ssid = (self.demo_ssid if preferred == "demo" else self.real_ssid) or either
                self._live_busy[preferred] = True
                threading.Thread(target=self._fill_live, args=(preferred, ssid), name=f"pocket-live-{preferred}", daemon=True).start()
            return
        if self._live_done[other] or self._live_busy[other]:
            return
        ssid = (self.demo_ssid if other == "demo" else self.real_ssid) or either
        self._live_busy[other] = True
        threading.Thread(target=self._fill_live, args=(other, ssid), name=f"pocket-live-{other}", daemon=True).start()

    def _fill_live(self, mode: str, ssid: str) -> None:
        is_demo = mode == "demo"
        try:
            found = read_session(ssid, is_demo, self.uid)
            if not found:
                return
            tagged = found.get("is_demo")
            if tagged is not None and bool(tagged) != is_demo:
                return
            other = self.real_balance if is_demo else self.demo_balance
            if tagged is None and other and found.get("balance") == other:
                return
            if is_demo and not self.demo_ssid:
                self.demo_ssid = format_ssid(ssid, True, self.uid)
            if not is_demo and not self.real_ssid:
                self.real_ssid = format_ssid(ssid, False, self.uid)
            self._mode = mode
            self._apply_balance(found)
            self._live_done[mode] = True
        finally:
            self._live_busy[mode] = False


def open_login(user_id: str, preferred_mode: str = "real", platform: str = "pocketoption") -> PocketLogin:
    try:
        code = normalize_platform(platform)
    except ValueError as exc:
        raise PocketLoginError(str(exc)) from exc
    session = PocketLogin(uuid.uuid4().hex, user_id, preferred_mode, code)
    session.start()
    with _LOCK:
        _SESSIONS[session.id] = session
    return session


def login_status(session_id: str, user_id: str) -> PocketLogin:
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if session is None or session.user_id != user_id:
        raise PocketLoginError("Open the options window again")
    return session


def close_login(session_id: str, user_id: str) -> None:
    session = login_status(session_id, user_id)
    session.close()
    shutil.rmtree(session.profile, ignore_errors=True)


def _blob_balance(payload: str) -> dict | None:
    text = str(payload or "").strip()
    if not text or text.startswith("42") or text.startswith("0") or text.startswith("40"):
        return None
    try:
        blob = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parse_session_payload(blob)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
