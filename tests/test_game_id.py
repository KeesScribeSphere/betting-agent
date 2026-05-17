from agent.exchange.overtime.game_id import decode_fixture_key, normalize_game_id


def test_normalize_game_id():
    assert normalize_game_id("ABC") == "0xabc"
    assert normalize_game_id("0xABC") == "0xabc"


def test_decode_fixture_key_from_bytes32():
    # ASCII "20260517A2C1EA5" padded in bytes32
    hex_id = "0x" + "323032363035313741324331454135".ljust(64, "0")
    assert decode_fixture_key(hex_id) == "20260517A2C1EA5"
