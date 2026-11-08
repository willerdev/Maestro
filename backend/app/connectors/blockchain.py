from __future__ import annotations

import re
from decimal import Decimal

import httpx

CHAINS = {
    "ethereum": {"label": "Ethereum", "symbol": "ETH", "rpc": "https://ethereum.publicnode.com", "kind": "evm"},
    "bnb": {"label": "BNB Chain", "symbol": "BNB", "rpc": "https://bsc-dataseed.binance.org", "kind": "evm"},
    "polygon": {"label": "Polygon", "symbol": "POL", "rpc": "https://polygon-bor-rpc.publicnode.com", "kind": "evm"},
    "bitcoin": {"label": "Bitcoin", "symbol": "BTC", "rpc": "https://blockstream.info/api", "kind": "btc"},
}

_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BTC = re.compile(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,62}$")
_SECRET_KEYS = ("private_key", "seed", "mnemonic", "secret")


def format_units(raw: int, decimals: int) -> str:
    amount = Decimal(raw) / (Decimal(10) ** decimals)
    text = f"{amount:.8f}".rstrip("0").rstrip(".")
    return text or "0"


def balance_of_data(wallet: str) -> str:
    return "0x70a08231" + wallet.lower().removeprefix("0x").rjust(64, "0")


def _fail(code: str, detail: str) -> dict:
    return {"ok": False, "status": "rejected", "error_code": code, "detail": detail, "region": "", "account": None}


def _address_ok(chain: str, value: str) -> bool:
    if CHAINS[chain]["kind"] == "btc":
        return bool(_BTC.match(value))
    return bool(_EVM.match(value))


def _rpc(url: str, method: str, params: list) -> str:
    response = httpx.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=12)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"]))
    result = body.get("result")
    if not isinstance(result, str) or not result.startswith("0x"):
        raise RuntimeError("The chain did not return a balance")
    return result


def read_native(chain: str, address: str) -> int:
    spec = CHAINS[chain]
    if spec["kind"] == "btc":
        response = httpx.get(f"{spec['rpc']}/address/{address}", timeout=12)
        response.raise_for_status()
        stats = response.json().get("chain_stats") or {}
        return int(stats.get("funded_txo_sum") or 0) - int(stats.get("spent_txo_sum") or 0)
    return int(_rpc(spec["rpc"], "eth_getBalance", [address, "latest"]), 16)


def read_token(chain: str, contract: str, wallet: str) -> tuple[int, int]:
    spec = CHAINS[chain]
    raw = _rpc(spec["rpc"], "eth_call", [{"to": contract, "data": balance_of_data(wallet)}, "latest"])
    decimals_raw = _rpc(spec["rpc"], "eth_call", [{"to": contract, "data": "0x313ce567"}, "latest"])
    decimals = int(decimals_raw, 16)
    if decimals < 0 or decimals > 36:
        decimals = 18
    return int(raw, 16), decimals


def _chain_spec(raw: dict) -> tuple[str, dict] | dict:
    if any(str(raw.get(key) or "").strip() for key in _SECRET_KEYS):
        return _fail("private_key_rejected", "Paste the public address only. Private keys and seed phrases are not accepted.")
    chain = str(raw.get("chain") or "").strip().lower()
    if chain not in CHAINS:
        return _fail("chain_required", "Choose Ethereum, BNB Chain, Polygon, or Bitcoin")
    return chain, CHAINS[chain]


def _account(spec: dict, name: str, number: str, server: str, amount: str, detail: str) -> dict:
    return {
        "ok": True,
        "status": "connected",
        "error_code": "",
        "detail": detail,
        "region": spec["label"],
        "account": {
            "display_name": name,
            "account_number": number,
            "broker": spec["label"],
            "server": server,
            "currency": spec["symbol"],
            "leverage": "1",
            "balance": amount,
            "equity": amount,
        },
    }


class BlockchainConnector:
    name = "blockchain"

    def inspect(self, credentials: dict) -> dict:
        raw = dict(credentials or {})
        spec = _chain_spec(raw)
        if isinstance(spec, dict):
            return spec
        chain, chain_spec = spec
        wallet = str(raw.get("wallet_address") or "").strip()
        contract = str(raw.get("contract_address") or "").strip()
        if chain_spec["kind"] == "btc":
            return _fail("contract_unsupported", "Contract reads are for Ethereum, BNB Chain, and Polygon.")
        if not wallet:
            return _fail("wallet_required", "A public wallet address is required")
        if not _address_ok(chain, wallet):
            return _fail("wallet_invalid", "That wallet address does not match the selected chain")
        if not contract:
            return _fail("contract_required", "A contract address is required")
        if not _address_ok(chain, contract):
            return _fail("contract_invalid", "That contract address does not match the selected chain")
        try:
            native = read_native(chain, wallet)
            amount, decimals = read_token(chain, contract, wallet)
        except Exception:
            return _fail("chain_unread", f"{chain_spec['label']} did not return the wallet or contract balance")
        native_text = format_units(native, 18)
        detail = f"Wallet {native_text} {chain_spec['symbol']} · Contract {format_units(amount, decimals)}"
        return _account(chain_spec, f"{chain_spec['label']} contract", wallet, "contracts", native_text, detail)


class MiningConnector:
    name = "mining"

    def inspect(self, credentials: dict) -> dict:
        raw = dict(credentials or {})
        spec = _chain_spec(raw)
        if isinstance(spec, dict):
            return spec
        chain, chain_spec = spec
        payout = str(raw.get("mining_address") or "").strip()
        worker = str(raw.get("worker") or "").strip()
        if not payout:
            return _fail("mining_required", "A mining payout address is required")
        if not _address_ok(chain, payout):
            return _fail("mining_invalid", "That mining payout address does not match the selected chain")
        if len(worker) > 64:
            return _fail("worker_invalid", "The worker name is too long")
        try:
            mined = read_native(chain, payout)
        except Exception:
            return _fail("chain_unread", f"{chain_spec['label']} did not return the mining payout balance")
        decimals = 8 if chain_spec["kind"] == "btc" else 18
        amount = format_units(mined, decimals)
        detail = f"Mining {amount} {chain_spec['symbol']}"
        if worker:
            detail = f"{detail} · {worker}"
        return _account(chain_spec, f"{chain_spec['label']} mining", payout, worker or "mining", amount, detail)
