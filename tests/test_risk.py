import tempfile
from pathlib import Path

import pytest

from agent.risk.manager import RiskManager
from agent.storage.repo import Repository


def test_risk_blocks_over_cap(sample_config):
    with tempfile.TemporaryDirectory() as tmp:
        sample_config.agent.db_path = str(Path(tmp) / "test.db")
        sample_config.agent.kill_switch_path = str(Path(tmp) / "kill.flag")
        repo = Repository(sample_config.agent.db_path)
        rm = RiskManager(sample_config, repo)
        decision = rm.check_trade(
            chain="base",
            stake_usdc=10,
            game_id="g1",
            liquidity_usd=100,
            total_bankroll_usdc=150,
            chain_usdc_balance=50,
            chain_eth_balance=0.01,
        )
        assert not decision.allowed
        assert decision.reason == "per_trade_cap"


def test_kill_switch_blocks(sample_config):
    with tempfile.TemporaryDirectory() as tmp:
        sample_config.agent.db_path = str(Path(tmp) / "test.db")
        flag = Path(tmp) / "kill.flag"
        sample_config.agent.kill_switch_path = str(flag)
        flag.write_text("manual stop")
        repo = Repository(sample_config.agent.db_path)
        rm = RiskManager(sample_config, repo)
        assert rm.is_kill_switch_active()
        decision = rm.check_trade(
            chain="base",
            stake_usdc=3,
            game_id="g1",
            liquidity_usd=100,
            total_bankroll_usdc=150,
            chain_usdc_balance=50,
            chain_eth_balance=0.01,
        )
        assert not decision.allowed
