"""Overtime adapter: subgraph quotes (default) + optional REST for execution quotes."""

from __future__ import annotations

from typing import Any

from agent.config import ChainConfig, OvertimeApiConfig
from agent.exchange.base import ExchangeAdapter, MarketQuote, TradeRequest, TradeResult
from agent.exchange.overtime.contracts import OvertimeContracts
from agent.exchange.overtime.rest import OvertimeRestClient
from agent.exchange.overtime.subgraph import OvertimeSubgraphClient
from agent.logging_setup import get_logger

log = get_logger(__name__)


class OvertimeAdapter(ExchangeAdapter):
    """Per-chain Overtime integration."""

    def __init__(
        self,
        chain_config: ChainConfig,
        api_config: OvertimeApiConfig,
        api_key: str | None = None,
        graph_api_key: str | None = None,
        private_key: str | None = None,
        simulate_trades: bool = False,
    ) -> None:
        self.chain = chain_config.name
        self.chain_id = chain_config.chain_id
        self._chain_config = chain_config
        self._simulate = simulate_trades
        self._data_source = api_config.data_source.lower()
        self._rest = OvertimeRestClient(
            base_url=api_config.base_url,
            chain_id=chain_config.chain_id,
            chain_name=chain_config.name,
            api_key=api_key,
        )
        self._subgraph = OvertimeSubgraphClient(
            chain_id=chain_config.chain_id,
            chain_name=chain_config.name,
            graph_api_key=graph_api_key,
        )
        self._contracts = OvertimeContracts(
            rpc_urls=chain_config.rpc_urls,
            chain_id=chain_config.chain_id,
            sports_amm_address=chain_config.sports_amm_v2,
            usdc_address=chain_config.usdc,
            private_key=None if simulate_trades else private_key,
        )

    async def close(self) -> None:
        await self._rest.close()
        await self._subgraph.close()

    async def fetch_market_quotes(self) -> list[MarketQuote]:
        if self._data_source == "rest":
            return await self._rest.fetch_market_quotes()

        try:
            return await self._subgraph.fetch_market_quotes()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "subgraph_fetch_failed",
                chain=self.chain,
                error=str(exc),
            )
            if self._data_source == "auto" and self._rest.api_key:
                return await self._rest.fetch_market_quotes()
            raise

    async def get_quote(self, request: TradeRequest) -> dict[str, Any]:
        if not self._rest.api_key:
            raise RuntimeError(
                "OVERTIME_API_KEY required for trade quotes. "
                "Overtime REST API access is gated — detection works via subgraph, "
                "but live/paper execution needs an approved API key or manual trades."
            )
        body = {
            "trades": [
                {
                    "gameId": request.game_id,
                    "sportId": 0,
                    "typeId": 0,
                    "position": request.side_index,
                    "buyInAmount": request.stake_usdc,
                    "collateral": request.collateral,
                }
            ],
            "buyInAmount": request.stake_usdc,
            "collateral": request.collateral,
        }
        return await self._rest.fetch_quotes(request.game_id, body)

    async def place_trade(self, request: TradeRequest, quote: dict[str, Any]) -> TradeResult:
        if self._simulate:
            log.info(
                "simulated_trade",
                chain=self.chain,
                game_id=request.game_id,
                side=request.side_index,
                stake=request.stake_usdc,
            )
            return TradeResult(
                success=True,
                tx_hash="simulated",
                chain=self.chain,
                simulated=True,
            )

        try:
            trade_data = quote.get("tradeData") or quote.get("contractTradeData")
            if trade_data is None:
                return TradeResult(
                    success=False,
                    tx_hash=None,
                    chain=self.chain,
                    error="No tradeData in quote response",
                )
            buy_in_wei = int(float(request.stake_usdc) * 10**6)
            await self._contracts.ensure_usdc_allowance(buy_in_wei)
            tx_hash = await self._contracts.trade(tuple(trade_data))
            return TradeResult(success=True, tx_hash=tx_hash, chain=self.chain)
        except Exception as exc:  # noqa: BLE001
            log.exception("trade_failed", chain=self.chain, error=str(exc))
            return TradeResult(success=False, tx_hash=None, chain=self.chain, error=str(exc))

    async def fetch_recent_tickets(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self._subgraph.fetch_recent_tickets(limit=limit)

    async def fetch_open_positions(self) -> list[dict[str, Any]]:
        return []

    async def get_balances(self, address: str) -> dict[str, float]:
        eth_wei = await self._contracts.get_eth_balance(address)
        usdc_raw = await self._contracts.get_usdc_balance(address)
        return {
            "eth": eth_wei / 10**18,
            "usdc": usdc_raw / 10**6,
        }
