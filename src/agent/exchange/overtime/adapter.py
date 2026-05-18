"""Overtime adapter: subgraph quotes + REST or on-chain execution."""

from __future__ import annotations

from typing import Any

from agent.config import ChainConfig, ExecutionConfig, OvertimeApiConfig
from agent.exchange.base import ExchangeAdapter, MarketQuote, TradeRequest, TradeResult
from agent.exchange.overtime.contracts import OvertimeContracts
from agent.exchange.overtime.onchain_trade import OnchainTradeClient
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
        execution_config: ExecutionConfig | None = None,
        api_key: str | None = None,
        graph_api_key: str | None = None,
        private_key: str | None = None,
        simulate_trades: bool = False,
    ) -> None:
        self.chain = chain_config.name
        self.chain_id = chain_config.chain_id
        self._chain_config = chain_config
        self._simulate = simulate_trades
        self._execution = execution_config or ExecutionConfig()
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
        self._onchain = OnchainTradeClient(
            rpc_urls=chain_config.rpc_urls,
            chain_id=chain_config.chain_id,
            sports_amm_address=chain_config.sports_amm_v2,
            usdc_address=chain_config.usdc,
        )
        self._contracts = OvertimeContracts(
            rpc_urls=chain_config.rpc_urls,
            chain_id=chain_config.chain_id,
            sports_amm_address=chain_config.sports_amm_v2,
            usdc_address=chain_config.usdc,
            private_key=None if simulate_trades else private_key,
        )

    def _use_rest_execution(self) -> bool:
        mode = self._execution.mode.lower()
        if mode == "rest":
            return True
        if mode == "onchain":
            return False
        return bool(self._rest.api_key)

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

    async def _market_quote_for_request(self, request: TradeRequest) -> MarketQuote:
        quotes = await self.fetch_market_quotes()
        for q in quotes:
            if (
                q.game_id == request.game_id
                and q.market_type == request.market_type
                and q.side_index == request.side_index
            ):
                return q
        raise ValueError(f"No subgraph quote for {request.game_id} {request.market_type} side {request.side_index}")

    async def get_quote(
        self,
        request: TradeRequest,
        quote: MarketQuote | None = None,
    ) -> dict[str, Any]:
        if self._use_rest_execution():
            body = {
                "trades": [
                    {
                        "gameId": request.game_id,
                        "sportId": request.sport_id,
                        "typeId": request.type_id,
                        "position": request.side_index,
                        "line": request.line,
                        "playerId": request.player_id,
                        "buyInAmount": request.stake_usdc,
                        "collateral": request.collateral,
                    }
                ],
                "buyInAmount": request.stake_usdc,
                "collateral": request.collateral,
            }
            return await self._rest.fetch_quotes(request.game_id, body)

        if quote is None:
            quote = await self._market_quote_for_request(request)
        rows = await self._subgraph.fetch_game_market_rows(request.game_id)
        trade_data = await self._onchain.build_trade_data(quote, rows, request.side_index)
        onchain_quote = await self._onchain.trade_quote(trade_data, request.stake_usdc)
        onchain_quote["execution"] = "onchain"
        return onchain_quote

    async def place_trade(self, request: TradeRequest, quote: dict[str, Any]) -> TradeResult:
        # Paper: optional on-chain tradeQuote dry-run already done in get_quote; no tx.
        if self._simulate:
            log.info(
                "simulated_trade",
                chain=self.chain,
                game_id=request.game_id,
                side=request.side_index,
                stake=request.stake_usdc,
                execution=quote.get("execution", "simulate"),
                risk_status=quote.get("riskStatus"),
                payout=quote.get("payout"),
            )
            return TradeResult(
                success=True,
                tx_hash="simulated",
                chain=self.chain,
                simulated=True,
            )

        try:
            if quote.get("execution") == "onchain" or not self._use_rest_execution():
                return await self._place_trade_onchain(request, quote)
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

    async def _place_trade_onchain(self, request: TradeRequest, quote: dict[str, Any]) -> TradeResult:
        from agent.exchange.overtime.onchain_trade import SPORTS_AMM_V2_QUOTE_ABI, _to_contract_trade_tuple

        trade_data = quote.get("tradeData")
        if not trade_data:
            return TradeResult(False, None, self.chain, error="missing tradeData")
        if not self._contracts._account:  # noqa: SLF001
            return TradeResult(False, None, self.chain, error="private key required")

        w3 = await self._contracts._web3()  # noqa: SLF001
        amm = w3.eth.contract(
            address=w3.to_checksum_address(self._chain_config.sports_amm_v2),
            abi=SPORTS_AMM_V2_QUOTE_ABI,
        )
        buy_in_wei = quote.get("buyInWei") or int(request.stake_usdc * 10**6)
        expected = quote["totalQuote"]
        slippage_wei = int(expected * request.slippage_pct / 100)
        from agent.util.addresses import checksum_address

        collateral = quote.get("collateral") or checksum_address(self._chain_config.usdc)
        trade_tuple = _to_contract_trade_tuple(trade_data)
        await self._contracts.ensure_usdc_allowance(buy_in_wei)
        tx = await amm.functions.trade(
            [trade_tuple],
            buy_in_wei,
            expected,
            slippage_wei,
            "0x0000000000000000000000000000000000000000",
            collateral,
            False,
        ).build_transaction(await self._contracts._build_base_tx(w3, self._contracts._account.address))  # noqa: SLF001
        tx_hash = await self._contracts._send_tx(w3, tx)  # noqa: SLF001
        return TradeResult(True, tx_hash, self.chain)

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
