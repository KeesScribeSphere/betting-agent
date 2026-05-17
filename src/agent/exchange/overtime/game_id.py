"""Helpers for Overtime gameId bytes32 values."""


def normalize_game_id(game_id_hex: str) -> str:
    if game_id_hex.startswith("0x"):
        return game_id_hex.lower()
    return f"0x{game_id_hex.lower()}"


def decode_fixture_key(game_id_hex: str) -> str | None:
    """Decode ASCII fixture id embedded in bytes32 gameId (e.g. 20260517A2C1EA5)."""
    try:
        raw = bytes.fromhex(normalize_game_id(game_id_hex)[2:])
        text = raw.rstrip(b"\x00").decode("ascii", errors="ignore").strip()
        return text or None
    except (ValueError, UnicodeDecodeError):
        return None
