"""SHA-256 hashing and Ed25519 wallet keys. Private keys stay with the caller."""

from __future__ import annotations

import hashlib
import json
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

ADDRESS = re.compile(r"^pcoin1[0-9a-f]{40}$")


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def meets_difficulty(digest: str, difficulty: int) -> bool:
    if difficulty < 0 or difficulty > 256 or len(digest) != 64:
        return False
    return int(digest, 16) < (1 << (256 - difficulty))


def address_for(public_hex: str) -> str:
    raw = bytes.fromhex(public_hex)
    if len(raw) != 32:
        raise ValueError("Public key must be 32 bytes")
    return "pcoin1" + hashlib.sha256(raw).hexdigest()[:40]


def new_keypair() -> tuple[str, str, str]:
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return private, public, address_for(public)


def public_from_private(private_hex: str) -> str:
    raw = bytes.fromhex(private_hex)
    if len(raw) != 32:
        raise ValueError("Private key must be 64 hex characters")
    key = Ed25519PrivateKey.from_private_bytes(raw)
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def sign_message(private_hex: str, message: bytes) -> str:
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    return key.sign(message).hex()


def verify_message(public_hex: str, message: bytes, signature_hex: str) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
        key.verify(bytes.fromhex(signature_hex), message)
    except Exception:
        return False
    return True
