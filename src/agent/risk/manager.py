"""Pre-trade risk controls."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from agent.config import AppConfig
from agent.storage.repo import Repository


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str = ""


class RiskManager:
    def __init__(self, config: AppConfig, repo: Repository) -> None:
        self.config = config
        self.repo = repo
        self._order_timestamps: dict[str, list[float]] = {}

    def is_kill_switch_active(self) -> bool:
        flag = Path(self.config.agent.kill_switch_path)
        if flag.exists():
            return True
        return False

    def trip_kill_switch(self, reason: str) -> None:
        Path(self.config.agent.kill_switch_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.config.agent.kill_switch_path).write_text(reason)
        self.repo.trip_kill_switch(reason)

    def check_trade(
        self,
        chain: str,
        stake_usdc: float,
        game_id: str,
        liquidity_usd: float | None,
        total_bankroll_usdc: float,
        chain_usdc_balance: float,
        chain_eth_balance: float,
    ) -> RiskDecision:
        risk = self.config.risk

        if self.is_kill_switch_active():
            return RiskDecision(False, "kill_switch_active")

        if total_bankroll_usdc > risk.max_bankroll_usdc:
            return RiskDecision(False, "bankroll_exceeds_cap")

        if stake_usdc > risk.per_trade_usdc_cap:
            return RiskDecision(False, "per_trade_cap")

        if chain_usdc_balance < stake_usdc:
            return RiskDecision(False, "insufficient_chain_usdc")

        if chain_eth_balance < risk.min_gas_eth:
            return RiskDecision(False, "insufficient_gas")

        if liquidity_usd is not None and liquidity_usd < stake_usdc * 2:
            return RiskDecision(False, "insufficient_liquidity")

        daily_pnl = self.repo.daily_loss_usdc()
        if daily_pnl <= -risk.daily_loss_cap_usdc:
            self.trip_kill_switch("daily_loss_cap")
            return RiskDecision(False, "daily_loss_cap")

        now = time.time()
        window = self._order_timestamps.setdefault(chain, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= risk.max_orders_per_chain_per_minute:
            return RiskDecision(False, "rate_limit")
        window.append(now)

        return RiskDecision(True)
