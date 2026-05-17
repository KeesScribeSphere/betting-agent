"""Cross-chain game_id + market_type grouping."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations

from agent.exchange.base import MarketQuote


@dataclass
class ChainMarketState:
    chain: str
    quotes_by_side: dict[int, MarketQuote] = field(default_factory=dict)


@dataclass
class UnifiedMarket:
    game_id: str
    market_type: str
    sport: str
    league: str
    kickoff: datetime | None
    chains: dict[str, ChainMarketState] = field(default_factory=dict)

    @property
    def mapping_confidence(self) -> float:
        return 1.0 if len(self.chains) >= 2 else 0.0

    def chain_pairs(self) -> list[tuple[str, str]]:
        names = sorted(self.chains.keys())
        return list(combinations(names, 2))


class GameMapper:
    """Group quotes by (game_id, market_type) across chains."""

    def group(self, quotes_by_chain: dict[str, list[MarketQuote]]) -> dict[tuple[str, str], UnifiedMarket]:
        unified: dict[tuple[str, str], UnifiedMarket] = {}

        for chain, quotes in quotes_by_chain.items():
            for quote in quotes:
                key = (quote.game_id, quote.market_type)
                if key not in unified:
                    unified[key] = UnifiedMarket(
                        game_id=quote.game_id,
                        market_type=quote.market_type,
                        sport=quote.sport,
                        league=quote.league,
                        kickoff=quote.kickoff,
                    )
                market = unified[key]
                if chain not in market.chains:
                    market.chains[chain] = ChainMarketState(chain=chain)
                market.chains[chain].quotes_by_side[quote.side_index] = quote

        return {k: v for k, v in unified.items() if v.mapping_confidence >= 1.0}
