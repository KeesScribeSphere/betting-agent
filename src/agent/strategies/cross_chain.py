"""Cross-chain skew arbitrage strategy (complementary legs = locked payout)."""

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
    leg1_chain: str
    leg1_side: int
    leg2_chain: str
    leg2_side: int
    combined_implied: float
    net_edge_pct: float
    stake_usdc: float
    type_id: int = 0
    line: int = 0
    player_id: int = 0
    sport_id: int = 0


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
        cost_pct = (
            self.config.cost_floor.overtime_fee_pct_per_leg * 2
            + self.config.cost_floor.slippage_pct_per_leg * 2
        )
        signals: list[ArbSignal] = []

        for market in unified.values():
            for chain_a, chain_b in market.chain_pairs():
                state_a = market.chains[chain_a]
                state_b = market.chains[chain_b]
                # Opposite sides across chains: buy cheap home + cheap away, etc.
                for side_a, qa in state_a.quotes_by_side.items():
                    qb_a = state_b.quotes_by_side.get(side_a)
                    if qb_a is None:
                        continue
                    for side_b, qb in state_b.quotes_by_side.items():
                        if side_b == side_a:
                            continue
                        qa_b = state_a.quotes_by_side.get(side_b)
                        if qa_b is None:
                            continue
                        prob_a = min(qa.implied_prob, qb_a.implied_prob)
                        prob_b = min(qb.implied_prob, qa_b.implied_prob)
                        combined = prob_a + prob_b
                        if combined >= 1.0:
                            continue
                        gross_edge_pct = (1.0 - combined) * 100
                        net_edge = gross_edge_pct - cost_pct
                        if net_edge < threshold:
                            continue
                        leg1_chain = chain_a if qa.implied_prob <= qb_a.implied_prob else chain_b
                        leg2_chain = chain_b if qb.implied_prob <= qa_b.implied_prob else chain_a
                        if leg1_chain == leg2_chain:
                            continue
                        ref = qa
                        signals.append(
                            ArbSignal(
                                game_id=market.game_id,
                                market_type=market.market_type,
                                leg1_chain=leg1_chain,
                                leg1_side=leg1_side,
                                leg2_chain=leg2_chain,
                                leg2_side=leg2_side,
                                combined_implied=combined,
                                net_edge_pct=net_edge,
                                stake_usdc=cap,
                                type_id=ref.market_type_id,
                                line=ref.line or 0,
                                player_id=ref.player_id or 0,
                                sport_id=ref.sport_id or 0,
                            )
                        )
        return signals

    def _trade_request(self, signal: ArbSignal, chain: str, side: int) -> TradeRequest:
        return TradeRequest(
            game_id=signal.game_id,
            market_type=signal.market_type,
            side_index=side,
            stake_usdc=signal.stake_usdc,
            type_id=signal.type_id,
            line=signal.line,
            player_id=signal.player_id,
            sport_id=signal.sport_id,
            chain=chain,
        )

    async def execute_signal(self, signal: ArbSignal) -> bool:
        arb_id = str(uuid.uuid4())[:8]
        log.info("arb_signal", arb_id=arb_id, **signal.__dict__)

        leg1 = self._trade_request(signal, signal.leg1_chain, signal.leg1_side)
        leg2 = self._trade_request(signal, signal.leg2_chain, signal.leg2_side)

        return await self.legs.execute_two_leg(
            arb_group_id=arb_id,
            leg1_chain=signal.leg1_chain,
            leg2_chain=signal.leg2_chain,
            leg1_request=leg1,
            leg2_request=leg2,
        )
