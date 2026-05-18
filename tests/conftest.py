import pytest

from agent.config import AppConfig, ChainConfig, CostFloorConfig, RiskConfig


@pytest.fixture
def sample_config() -> AppConfig:
    return AppConfig(
        cost_floor=CostFloorConfig(min_edge_pct=6.0, safety_buffer_pct=0.5),
        risk=RiskConfig(max_bankroll_usdc=200, per_trade_usdc_cap=5),
        chains={
            "base": ChainConfig(
                chain_id=8453,
                name="base",
                rpc_urls=["https://mainnet.base.org"],
                sports_amm_v2="0xa1ead27ebbd90b8ef385f264cc66ba4c96767fdf",
                usdc="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            ),
            "optimism": ChainConfig(
                chain_id=10,
                name="optimism",
                rpc_urls=["https://mainnet.optimism.io"],
                sports_amm_v2="0xFb4e4811C7A811E098A556bD79B64c20b479E431",
                usdc="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
            ),
        },
    )
