"""Cross-chain skew arbitrage strategy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from agent.config import AppConfig
from agent.exchange.base import TradeRequest
from agent.logging_setup import get_logger
from agent.mapper.game_mapper import UnifiedMarket
from agent.risk.manager import RiskManager
from agent.strategies.leg_coordinator import LegCoordinator

log = get_logger(__name__)


@dataclass(frozen=True)
class ArbSignal:
    game_id: str
    market_type: str
    side_index: int
    chain_skewed: str
    chain_favorable: str
    gap_pct: float
    net_gap_pct: float
    stake_usdc: float


class CrossChainStrategy:
    def __init__(
        self,
        config: AppConfig,
        risk: RiskManager,
        leg_coordinator: LegCoordinator,
    ) -> None:
        self.config = config
        self.risk = risk
        self.legs = leg_coordinator

    def find_signals(self, unified: dict[tuple[str, str], UnifiedMarket]) -> list[ArbSignal]:
        threshold = self.config.cost_floor.threshold_pct
        cap = self.config.risk.per_trade_usdc_cap
        signals: list[ArbSignal] = []

        for market in unified.values():
            for chain_a, chain_b in market.chain_pairs():
                state_a = market.chains[chain_a]
                state_b = market.chains[chain_b]
                for side, qa in state_a.quotes_by_side.items():
                    qb = state_b.quotes_by_side.get(side)
                    if not qb:
                        continue
                    gap_pct = abs(qa.implied_prob - qb.implied_prob) * 100
                    cost = (
                        self.config.cost_floor.overtime_fee_pct_per_leg * 2
                        + self.config.cost_floor.slippage_pct_per_leg * 2
                    )
                    net_gap = gap_pct - cost
                    if net_gap < threshold:
                        continue
                    if qa.implied_prob > qb.implied_prob:
                        skewed, favorable = chain_a, chain_b
                    else:
                        skewed, favorable = chain_b, chain_a
                    signals.append(
                        ArbSignal(
                            game_id=market.game_id,
                            market_type=market.market_type,
                            side_index=side,
                            chain_skewed=skewed,
                            chain_favorable=favorable,
                            gap_pct=gap_pct,
                            net_gap_pct=net_gap,
                            stake_usdc=cap,
                        )
                    )
        return signals

    async def execute_signal(self, signal: ArbSignal) -> bool:
        arb_id = str(uuid.uuid4())[:8]
        log.info("arb_signal", arb_id=arb_id, **signal.__dict__)

        leg1 = TradeRequest(
            game_id=signal.game_id,
            market_type=signal.market_type,
            side_index=signal.side_index,
            stake_usdc=signal.stake_usdc,
        )
        leg2 = TradeRequest(
            game_id=signal.game_id,
            market_type=signal.market_type,
            side_index=signal.side_index,
            stake_usdc=signal.stake_usdc,
        )

        return await self.legs.execute_two_leg(
            arb_group_id=arb_id,
            leg1_chain=signal.chain_skewed,
            leg2_chain=signal.chain_favorable,
            leg1_request=leg1,
            leg2_request=leg2,
        )
