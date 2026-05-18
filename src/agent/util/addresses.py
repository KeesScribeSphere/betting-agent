"""EIP-55 address normalization."""

from __future__ import annotations

from eth_utils import to_checksum_address


def checksum_address(addr: str) -> str:
    raw = addr if addr.startswith("0x") else f"0x{addr}"
    hex_body = raw[2:]
    if len(hex_body) != 40:
        raise ValueError(f"Invalid address length ({len(hex_body)} hex chars): {raw}")
    return to_checksum_address(raw.lower())
