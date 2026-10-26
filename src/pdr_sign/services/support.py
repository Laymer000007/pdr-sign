"""Support details shown in the welcome window and About: donations, feedback, issues.

PDR Sign is free; donations are voluntary. The Zcash address is checked (Base58Check
and the mainnet transparent prefix) by a unit test, so a typo can't ship.
"""

from __future__ import annotations

import hashlib

from pdr_sign import SOURCE_URL

ZCASH_ADDRESS = "t1J43HtBcvFmtYmJF7waapPcJtKHUwDY8mf"
FEEDBACK_EMAIL = "micro_korn@hotmail.com"
ISSUES_URL = f"{SOURCE_URL}/issues"
MILESTONES = (
    "Digital certificate signatures",
    "Highlight, underline and comments",
    "Rotate, reorder and delete pages",
    "Merge and split PDFs",
    "Text recognition (OCR) for scanned documents",
)

_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# Zcash mainnet transparent prefixes: t1… pay-to-pubkey-hash, t3… pay-to-script-hash.
_T_PREFIXES = (bytes((0x1C, 0xB8)), bytes((0x1C, 0xBD)))


def base58check_decode(text: str) -> bytes | None:
    """The payload (without the 4-byte checksum), or None if it isn't valid."""
    number = 0
    for char in text:
        digit = _BASE58.find(char)
        if digit < 0:
            return None
        number = number * 58 + digit
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    raw = b"\0" * (len(text) - len(text.lstrip("1"))) + raw
    if len(raw) < 5:
        return None
    payload, checksum = raw[:-4], raw[-4:]
    digest = hashlib.sha256(hashlib.sha256(payload).digest()).digest()
    return payload if digest[:4] == checksum else None


def is_zcash_transparent_address(text: str) -> bool:
    """A valid mainnet t-address: 2-byte prefix + 20-byte hash, correct checksum."""
    payload = base58check_decode(text)
    return payload is not None and len(payload) == 22 and payload[:2] in _T_PREFIXES


def zcash_uri(address: str = ZCASH_ADDRESS) -> str:
    """A ZIP-321 payment URI (``zcash:<address>``), for the QR code."""
    return f"zcash:{address}"


def mailto_url(address: str = FEEDBACK_EMAIL) -> str:
    return f"mailto:{address}?subject=PDR%20Sign%20feedback"
