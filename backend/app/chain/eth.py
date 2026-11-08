"""Derive an Ethereum address from a secp256k1 private key. Keys are not logged here."""

from __future__ import annotations

import re

from cryptography.hazmat.primitives.asymmetric import ec

_HEX = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_MASK = (1 << 64) - 1
_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 8),
    (27, 20, 39, 8, 14),
)


def keccak256(data: bytes) -> bytes:
    rate = 136
    lanes = [[0] * 5 for _ in range(5)]
    padded = bytearray(data) + b"\x01"
    pad = rate - (len(padded) % rate)
    padded.extend(b"\x00" * (pad - 1) + b"\x80")
    for start in range(0, len(padded), rate):
        block = padded[start : start + rate]
        for i in range(rate // 8):
            word = int.from_bytes(block[i * 8 : (i + 1) * 8], "little")
            lanes[i % 5][i // 5] ^= word
        _keccak_f(lanes)
    out = bytearray()
    for i in range(4):
        out.extend(lanes[i % 5][i // 5].to_bytes(8, "little"))
    return bytes(out)


def _keccak_f(lanes: list[list[int]]) -> None:
    for round_const in _RC:
        column = [lanes[x][0] ^ lanes[x][1] ^ lanes[x][2] ^ lanes[x][3] ^ lanes[x][4] for x in range(5)]
        delta = [column[(x - 1) % 5] ^ _rot(column[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                lanes[x][y] ^= delta[x]
        rotated = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                rotated[y][(2 * x + 3 * y) % 5] = _rot(lanes[x][y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                lanes[x][y] = rotated[x][y] ^ ((~rotated[(x + 1) % 5][y] & _MASK) & rotated[(x + 2) % 5][y])
        lanes[0][0] ^= round_const


def _rot(value: int, shift: int) -> int:
    shift %= 64
    return ((value << shift) | (value >> (64 - shift))) & _MASK


def parse_private_key(raw: str) -> bytes:
    text = raw.strip().replace(" ", "")
    if any(word in text.lower() for word in ("mnemonic", "seed")) or " " in raw.strip():
        raise ValueError("Paste a 64-character private key, not a seed phrase")
    if not _HEX.match(text):
        raise ValueError("The private key must be 64 hex characters")
    secret = bytes.fromhex(text.removeprefix("0x").removeprefix("0X"))
    scalar = int.from_bytes(secret, "big")
    if scalar <= 0 or scalar >= _N:
        raise ValueError("That private key is not a valid secp256k1 scalar")
    return secret


def address_from_private(raw: str) -> str:
    secret = parse_private_key(raw)
    key = ec.derive_private_key(int.from_bytes(secret, "big"), ec.SECP256K1())
    numbers = key.public_key().public_numbers()
    public = numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    return "0x" + keccak256(public)[-20:].hex()


def parse_address(raw: str) -> str:
    text = raw.strip()
    if not _ADDRESS.match(text):
        raise ValueError("Enter a public address that starts with 0x")
    return text
