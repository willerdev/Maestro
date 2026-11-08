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

from app.connectors.pocketoption import format_ssid, parse_auth_frame, parse_balance_frame, parse_session_payload, read_session

_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_LOGIN = "https://pocketoption.com/en/login"
_ROOT = Path(__file__).resolve().parents[4] / ".runtime" / "pocket-chrome"
_LOCK = threading.Lock()
_SESSIONS: dict[str, "PocketLogin"] = {}


class PocketLoginError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


class PocketLogin:
    def __init__(self, session_id: str, user_id: str, preferred_mode: str = "real") -> None:
        self.id = session_id
        self.user_id = user_id
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
        self._mode = ""
        self._pending_balance: dict | None = None
        self._live_done = {"demo": False, "real": False}
        self._live_busy = {"demo": False, "real": False}

    def start(self) -> None:
        if not Path(_CHROME).exists():
            raise PocketLoginError("Google Chrome is not installed, so the Pocket Option window cannot open")
        self.profile.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            [
                _CHROME,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-allow-origins=*",
                "--new-window",
                _LOGIN,
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
            detail = f"Sign in on {book} in the Pocket Option window. That book is read first. You can switch after."
        return {
            "id": self.id,
            "status": "failed" if self.error else ("captured" if ready else "waiting"),
            "detail": detail,
            "uid": self.uid,
            "preferred_mode": self.preferred_mode,
            "demo": demo,
            "real": real,
        }

    def _book(self, mode: str) -> dict | None:
        ssid = self.demo_ssid if mode == "demo" else self.real_ssid
        balance = self.demo_balance if mode == "demo" else self.real_balance
        currency = self.demo_currency if mode == "demo" else self.real_currency
        other = self.real_ssid if mode == "demo" else self.demo_ssid
        if not ssid and not balance and not (self.preferred_mode == mode and other):
            return None
        return {"uid": self.uid, "balance": balance or "—", "currency": currency or "USD"}

    def credentials(self) -> dict:
        if not self.uid or not (self.demo_ssid or self.real_ssid):
            raise PocketLoginError("Sign in inside the Pocket Option window first")
        demo_ssid = self.demo_ssid or (format_ssid(self.real_ssid, True, self.uid) if self.preferred_mode == "demo" else "")
        real_ssid = self.real_ssid or (format_ssid(self.demo_ssid, False, self.uid) if self.preferred_mode == "real" else "")
        return {
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
                self.error = "The Pocket Option window stopped before a session was captured"

    async def _collect(self) -> None:
        seen: set[str] = set()
        for _ in range(300):
            if self.closed:
                return
            try:
                response = httpx.get(f"http://127.0.0.1:{self.port}/json", timeout=2)
                targets = response.json()
            except Exception:
                await asyncio.sleep(0.4)
                continue
            for target in targets:
                address = str(target.get("webSocketDebuggerUrl") or "")
                if target.get("type") != "page" or not address or address in seen:
                    continue
                seen.add(address)
                asyncio.create_task(self._attach(address))
            await asyncio.sleep(1)

    async def _attach(self, address: str) -> None:
        try:
            async with websockets.connect(address, open_timeout=5, max_size=8_000_000) as socket:
                await socket.send(json.dumps({"id": 1, "method": "Network.enable"}))
                while not self.closed:
                    raw = await asyncio.wait_for(socket.recv(), 30)
                    message = json.loads(raw)
                    params = message.get("params") or {}
                    payload = ""
                    if message.get("method") in {"Network.webSocketFrameSent", "Network.webSocketFrameReceived"}:
                        frame = params.get("response") or {}
                        payload = str(frame.get("payloadData") or "")
                        if frame.get("opcode") == 2 and payload:
                            try:
                                payload = base64.b64decode(payload).decode("utf-8", "replace")
                            except Exception:
                                payload = ""
                    self._note(payload)
        except Exception:
            return

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
            if self._pending_balance:
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

    def _kick_live(self) -> None:
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
            if found.get("is_demo") is not None and bool(found.get("is_demo")) != is_demo:
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


def open_login(user_id: str, preferred_mode: str = "real") -> PocketLogin:
    session = PocketLogin(uuid.uuid4().hex, user_id, preferred_mode)
    session.start()
    with _LOCK:
        _SESSIONS[session.id] = session
    return session


def login_status(session_id: str, user_id: str) -> PocketLogin:
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if session is None or session.user_id != user_id:
        raise PocketLoginError("Open the Pocket Option window again")
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
