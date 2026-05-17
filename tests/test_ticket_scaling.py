from agent.exchange.overtime.subgraph import _scaled_amount


def test_usdc_buy_in_scaled_to_human():
    usdc = "0xaf88d065e77c8cc2239327c5edb3a432268e5831"
    assert _scaled_amount("190000000", usdc) == 190.0


def test_weth_buy_in_uses_18_decimals():
    weth = "0x4200000000000000000000000000000000000006"
    assert abs(_scaled_amount("18729320000000000", weth) - 0.01872932) < 1e-8


def test_thales_buy_in_uses_18_decimals():
    thales = "0x7750c092e284e2c7366f50c8306f43c7eb2e82a2"
    assert abs(_scaled_amount("91276812000000000000", thales) - 91.276812) < 1e-3
