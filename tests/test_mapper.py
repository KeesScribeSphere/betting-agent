from datetime import UTC, datetime

from agent.exchange.base import MarketQuote
from agent.mapper.game_mapper import GameMapper


def _quote(chain: str, chain_id: int, game_id: str, side: int, prob: float) -> MarketQuote:
    return MarketQuote(
        chain=chain,
        chain_id=chain_id,
        game_id=game_id,
        market_type="winner",
        market_type_id=0,
        side_index=side,
        side_label="home" if side == 0 else "away",
        implied_prob=prob,
        decimal_odds=1 / prob,
        liquidity_usd=1000.0,
        sport="Soccer",
        league="Test League",
        kickoff=datetime.now(UTC),
        market_address=None,
    )


def test_game_mapper_groups_cross_chain():
    mapper = GameMapper()
    quotes = {
        "base": [_quote("base", 8453, "game1", 0, 0.45)],
        "optimism": [_quote("optimism", 10, "game1", 0, 0.50)],
    }
    unified = mapper.group(quotes)
    assert ("game1", "winner") in unified
    assert len(unified[("game1", "winner")].chains) == 2
