from agent.exchange.overtime.subgraph import (
    DEFAULT_GRAPH_API_KEY,
    _decode_game_id,
    _market_type_key,
    _odd_to_implied,
)


def test_odd_to_implied():
    assert abs(_odd_to_implied("500000000000000000") - 0.5) < 0.001


def test_market_type_key_includes_line():
    assert _market_type_key(10001, -150) == "type_10001_line_-150"
    assert _market_type_key(0, 0) == "type_0"


def test_market_type_key_includes_player():
    assert _market_type_key(11038, 250, 100031) == "type_11038_line_250_player_100031"


def test_decode_game_id():
    assert _decode_game_id("0xABC").startswith("0x")


def test_default_graph_key_is_set():
    assert len(DEFAULT_GRAPH_API_KEY) > 10
