from __future__ import annotations

"""
Program addresses, derived rather than asked for.

pump.fun's API is the discovery feed and it does not answer for every coin -
the newest ones, and some it has dropped, come back empty. That used to cost
the chart, because the bonding curve account is what the live candles are
read from and the only place it came from was that API.

It does not have to. The curve is a program derived address over the mint, so
it can be computed from the mint alone, offline, with no call to anybody. What
that takes is the standard derivation: hash the seeds with a bump byte and the
program id, and accept the first result that is NOT a valid ed25519 point,
which is what makes an address one no private key can sign for.
"""

import hashlib

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CURVE_SEED = b"bonding-curve"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_P = 2 ** 255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def b58decode(value: str) -> bytes:
    number = 0
    for char in value:
        index = _B58.find(char)
        if index < 0:
            raise ValueError(f"not base58: {char!r}")
        number = number * 58 + index
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    pad = len(value) - len(value.lstrip("1"))
    return b"\x00" * pad + raw


def b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rest = divmod(number, 58)
        out = _B58[rest] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def _on_curve(raw: bytes) -> bool:
    """
    Whether these 32 bytes decompress to a point on ed25519. A program derived
    address is defined as one that does not, so this is the test the loop below
    is looking to fail.
    """
    if len(raw) != 32:
        return False
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _P:
        return False
    y2 = (y * y) % _P
    numerator = (y2 - 1) % _P
    denominator = (_D * y2 + 1) % _P
    if denominator == 0:
        return False
    x2 = (numerator * pow(denominator, _P - 2, _P)) % _P
    if x2 == 0:
        return True
    # x2 is a square modulo p exactly when x2 ** ((p - 1) / 2) is 1
    return pow(x2, (_P - 1) // 2, _P) == 1


def find_program_address(seeds: list[bytes], program_id: str) -> tuple[str, int]:
    program = b58decode(program_id)
    joined = b"".join(seeds)
    for bump in range(255, -1, -1):
        digest = hashlib.sha256(joined + bytes([bump]) + program + b"ProgramDerivedAddress").digest()
        if not _on_curve(digest):
            return b58encode(digest), bump
    raise ValueError("no bump produced an off-curve address")


def bonding_curve(mint: str) -> str:
    """The pump.fun curve account for a mint, computed rather than looked up."""
    try:
        return find_program_address([CURVE_SEED, b58decode(mint)], PUMPFUN_PROGRAM)[0]
    except ValueError:
        return ""
