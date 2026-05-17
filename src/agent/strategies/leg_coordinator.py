"""Two-leg execution coordinator."""

from __future__ import annotations

import asyncio

from agent.exchange.base import TradeRequest
from agent.exchange.overtime.adapter import OvertimeAdapter
from agent.logging_setup import get_logger
from agent.storage.models import PlacedBet
from agent.storage.repo import Repository

log = get_logger(__name__)


class LegCoordinator:
    def __init__(
        self,
        adapters: dict[str, OvertimeAdapter],
        repo: Repository,
        leg2_timeout_seconds: float = 5.0,
        closeout_slippage_pct: float = 5.0,
    ) -> None:
        self.adapters = adapters
        self.repo = repo
        self.leg2_timeout = leg2_timeout_seconds
        self.closeout_slippage_pct = closeout_slippage_pct

    async def execute_two_leg(
        self,
        arb_group_id: str,
        leg1_chain: str,
        leg2_chain: str,
        leg1_request: TradeRequest,
        leg2_request: TradeRequest,
    ) -> bool:
        adapter1 = self.adapters[leg1_chain]
        adapter2 = self.adapters[leg2_chain]

        quote1 = await adapter1.get_quote(leg1_request)
        result1 = await adapter1.place_trade(leg1_request, quote1)
        self.repo.record_bet(
            PlacedBet(
                game_id=leg1_request.game_id,
                market_type=leg1_request.market_type,
                chain=leg1_chain,
                side_index=leg1_request.side_index,
                stake_usdc=leg1_request.stake_usdc,
                tx_hash=result1.tx_hash,
                simulated=result1.simulated,
                leg=1,
                arb_group_id=arb_group_id,
            )
        )

        if not result1.success:
            log.warning("leg1_failed", chain=leg1_chain, error=result1.error)
            return False

        try:
            quote2 = await asyncio.wait_for(
                adapter2.get_quote(leg2_request),
                timeout=self.leg2_timeout,
            )
            result2 = await asyncio.wait_for(
                adapter2.place_trade(leg2_request, quote2),
                timeout=self.leg2_timeout,
            )
        except TimeoutError:
            log.error("leg2_timeout", chain=leg2_chain, arb_group_id=arb_group_id)
            await self._closeout_leg1(leg1_chain, leg1_request, quote1)
            return False

        self.repo.record_bet(
            PlacedBet(
                game_id=leg2_request.game_id,
                market_type=leg2_request.market_type,
                chain=leg2_chain,
                side_index=leg2_request.side_index,
                stake_usdc=leg2_request.stake_usdc,
                tx_hash=result2.tx_hash,
                simulated=result2.simulated,
                leg=2,
                arb_group_id=arb_group_id,
            )
        )

        if not result2.success:
            log.error("leg2_failed_unhedged", chain=leg2_chain, arb_group_id=arb_group_id)
            await self._closeout_leg1(leg1_chain, leg1_request, quote1)
            return False

        return True

    async def _closeout_leg1(
        self,
        chain: str,
        request: TradeRequest,
        quote: dict,
    ) -> None:
        log.warning(
            "closeout_attempt",
            chain=chain,
            game_id=request.game_id,
            slippage_pct=self.closeout_slippage_pct,
        )
        close_request = TradeRequest(
            game_id=request.game_id,
            market_type=request.market_type,
            side_index=request.side_index,
            stake_usdc=request.stake_usdc,
            slippage_pct=self.closeout_slippage_pct,
        )
        adapter = self.adapters[chain]
        try:
            close_quote = await adapter.get_quote(close_request)
            await adapter.place_trade(close_request, close_quote or quote)
        except Exception as exc:  # noqa: BLE001
            log.exception("closeout_failed", error=str(exc))
