from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import threading
import uuid
from pathlib import Path

import httpx
import websockets

from app.connectors.pocketoption import parse_auth_frame, parse_balance_frame

_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_LOGIN = "https://pocketoption.com/en/login"
_ROOT = Path(__file__).resolve().parents[4] / ".runtime" / "pocket-chrome"
_LOCK = threading.Lock()
_SESSIONS: dict[str, "PocketLogin"] = {}


class PocketLoginError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


class PocketLogin:
    def __init__(self, session_id: str, user_id: str) -> None:
        self.id = session_id
        self.user_id = user_id
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
        demo = _side(self.demo_ssid, self.demo_balance, self.demo_currency, self.uid)
        real = _side(self.real_ssid, self.real_balance, self.real_currency, self.uid)
        return {
            "id": self.id,
            "status": "failed" if self.error else ("captured" if demo or real else "waiting"),
            "detail": self.error or "Sign in inside the Pocket Option window. Open Demo and Real so both balances can be read.",
            "uid": self.uid,
            "demo": demo,
            "real": real,
        }

    def credentials(self) -> dict:
        if not self.uid or not (self.demo_ssid or self.real_ssid):
            raise PocketLoginError("Sign in inside the Pocket Option window first")
        return {
            "uid": self.uid,
            "demo_ssid": self.demo_ssid,
            "real_ssid": self.real_ssid,
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
                        payload = str((params.get("response") or {}).get("payloadData") or "")
                    self._note(payload)
        except Exception:
            return

    def _note(self, payload: str) -> None:
        auth = parse_auth_frame(payload)
        if auth:
            self.uid = auth["uid"]
            self._mode = "demo" if auth["is_demo"] else "real"
            if auth["is_demo"]:
                self.demo_ssid = auth["wire"]
            else:
                self.real_ssid = auth["wire"]
            return
        found = parse_balance_frame(payload)
        if not found or not self._mode:
            return
        if self._mode == "demo":
            self.demo_balance = found["balance"]
            self.demo_currency = found["currency"]
        else:
            self.real_balance = found["balance"]
            self.real_currency = found["currency"]


def open_login(user_id: str) -> PocketLogin:
    session = PocketLogin(uuid.uuid4().hex, user_id)
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


def _side(ssid: str, balance: str, currency: str, uid: str) -> dict | None:
    if not ssid:
        return None
    return {"uid": uid, "balance": balance or "—", "currency": currency or "USD"}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
