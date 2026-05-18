"""Exchange adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MarketQuote:
    """Normalized quote for one side of a market on one chain."""

    chain: str
    chain_id: int
    game_id: str
    market_type: str
    market_type_id: int
    side_index: int
    side_label: str
    implied_prob: float
    decimal_odds: float
    liquidity_usd: float | None
    sport: str
    league: str
    kickoff: datetime | None
    market_address: str | None
    sport_id: int | None = None
    line: int | None = None
    player_id: int | None = None
    status: int | None = None
    odd_raw: float | None = None
    fixture_key: str | None = None
    subgraph_market_id: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class TradeRequest:
    game_id: str
    market_type: str
    side_index: int
    stake_usdc: float
    slippage_pct: float = 2.0
    collateral: str = "USDC"
    type_id: int = 0
    line: int = 0
    player_id: int = 0
    sport_id: int = 0
    chain: str | None = None


@dataclass(frozen=True)
class TradeResult:
    success: bool
    tx_hash: str | None
    chain: str
    error: str | None = None
    simulated: bool = False


class ExchangeAdapter(ABC):
    chain: str
    chain_id: int

    @abstractmethod
    async def fetch_market_quotes(self) -> list[MarketQuote]:
        """Return all open market quotes on this chain."""

    @abstractmethod
    async def get_quote(self, request: TradeRequest) -> dict[str, Any]:
        """Fetch trade quote from API for sizing."""

    @abstractmethod
    async def place_trade(self, request: TradeRequest, quote: dict[str, Any]) -> TradeResult:
        """Execute trade on-chain (or simulate)."""

    @abstractmethod
    async def fetch_open_positions(self) -> list[dict[str, Any]]:
        """Return open positions for reconciliation."""
