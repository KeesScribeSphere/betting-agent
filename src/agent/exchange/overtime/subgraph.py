"""Overtime SportsMarketsV2 subgraph client (no Overtime REST API key required).

Uses the public Graph gateway URLs published in thales-markets/thales-data (same
endpoints the Overtime frontend uses). Optional THEGRAPH_API_KEY overrides the
default key if you register your own at https://thegraph.com/studio/ (free tier).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from agent.exchange.base import MarketQuote
from agent.exchange.overtime.game_id import decode_fixture_key, normalize_game_id
from agent.exchange.overtime.rest import _side_label
from agent.logging_setup import get_logger

log = get_logger(__name__)

# Subgraph deployment / ID map (from thales-markets/thales-data constants.js)
SUBGRAPH_V2_BY_CHAIN_ID: dict[int, str] = {
    10: "DSxiPB7bWCBU4Aw1gsqSPJ72Usk4STbiWQSnQRn9YGD4",  # Optimism
    42161: "BRtus5QB7fZzKBAtMEm4KyhJyGCKWPoGGiMiQzqdFmfv",  # Arbitrum
}

SUBGRAPH_V2_DEPLOYMENT_BY_CHAIN_ID: dict[int, str] = {
    8453: "QmaqaeqMkRCi17XJMVm7b18dWvTRDuFHJ2y1fVA9fpUxJZ",  # Base (deployment id)
}

# Default Graph API key from thales-data (public in Overtime open-source frontend tooling)
DEFAULT_GRAPH_API_KEY = "d19a6a80c2d5a004e62041171d5f4c64"

GAME_MARKETS_QUERY = """
query GameMarkets($gameId: String!) {
  markets(where: { gameId: $gameId, status: 0 }) {
    gameId
    sportId
    typeId
    line
    maturity
    status
    position
    odd
    playerId
  }
}
"""

MARKETS_QUERY = """
query OpenMarkets($maturityGte: BigInt!, $skip: Int!) {
  markets(
    first: 1000
    skip: $skip
    where: { maturity_gte: $maturityGte, status: 0 }
    orderBy: maturity
    orderDirection: asc
  ) {
    id
    gameId
    sportId
    typeId
    line
    maturity
    status
    position
    odd
    playerId
  }
}
"""

TICKETS_QUERY = """
query RecentTickets($first: Int!) {
  tickets(first: $first, orderBy: timestamp, orderDirection: desc) {
    id
    txHash
    timestamp
    buyInAmount
    payout
    isLive
    fees
    collateral
    markets {
      gameId
      typeId
      line
      position
      odd
      playerId
    }
  }
}
"""

# Collateral token decimals (addresses are lowercase checksummed-agnostic)
_COLLATERAL_DECIMALS: dict[str, int] = {
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": 6,  # USDC (Base)
    "0x0b2c639c5338137c4aa58b0cae1a9cfbe376e89fd": 6,  # USDC (Optimism)
    "0xaf88d065e77c8cc2239327c5edb3a432268e5831": 6,  # USDC (Arbitrum)
    "0x4200000000000000000000000000000000000006": 18,  # WETH (canonical L2)
    "0x7750c092e284e2c7366f50c8306f43c7eb2e82a2": 18,  # THALES
}


def _collateral_decimals(collateral: str | None) -> int:
    if not collateral:
        return 6
    return _COLLATERAL_DECIMALS.get(collateral.lower(), 18)


def _scaled_amount(raw: str | int | None, collateral: str | None = None) -> float | None:
    if raw is None:
        return None
    value = float(raw)
    if value == 0:
        return 0.0
    decimals = _collateral_decimals(collateral)
    human = value / (10**decimals)
    # Legacy mis-scale guard: USDC-sized raw stored with 6 divisor on 18-dec token
    if human > 1_000_000 and decimals == 6:
        human = value / 1e18
    return human


def _market_type_key(type_id: int, line: int, player_id: int = 0) -> str:
    """Unique market key for cross-chain grouping (includes player props)."""
    if line == 0:
        key = f"type_{type_id}"
    else:
        key = f"type_{type_id}_line_{line}"
    if player_id != 0:
        key = f"{key}_player_{player_id}"
    return key


def _odd_to_implied(odd_raw: str | int) -> float:
    """Subgraph stores normalized implied weight at 1e18 scale."""
    return float(odd_raw) / 1e18


def _decode_game_id(game_id_hex: str) -> str:
    """Normalize gameId to 0x-prefixed hex string for cross-chain matching."""
    return normalize_game_id(game_id_hex)


class OvertimeSubgraphClient:
    def __init__(
        self,
        chain_id: int,
        chain_name: str,
        graph_api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.chain_id = chain_id
        self.chain_name = chain_name
        api_key = graph_api_key or DEFAULT_GRAPH_API_KEY
        self._url = self._build_url(chain_id, api_key)
        self._client = httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def _build_url(chain_id: int, api_key: str) -> str:
        base = f"https://gateway-arbitrum.network.thegraph.com/api/{api_key}"
        if chain_id in SUBGRAPH_V2_BY_CHAIN_ID:
            sid = SUBGRAPH_V2_BY_CHAIN_ID[chain_id]
            return f"{base}/subgraphs/id/{sid}"
        if chain_id in SUBGRAPH_V2_DEPLOYMENT_BY_CHAIN_ID:
            dep = SUBGRAPH_V2_DEPLOYMENT_BY_CHAIN_ID[chain_id]
            return f"{base}/deployments/id/{dep}"
        raise ValueError(f"No SportsMarketsV2 subgraph configured for chain_id {chain_id}")

    async def close(self) -> None:
        await self._client.aclose()

    async def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(
            self._url,
            json={"query": query, "variables": variables},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise RuntimeError(f"Subgraph errors: {body['errors']}")
        return body.get("data") or {}

    async def fetch_game_market_rows(self, game_id: str) -> list[dict[str, Any]]:
        data = await self._graphql(GAME_MARKETS_QUERY, {"gameId": game_id})
        return list(data.get("markets") or [])

    async def fetch_open_market_rows(self) -> list[dict[str, Any]]:
        """Paginate all open V2 market sides (status=0, maturity >= now)."""
        maturity_gte = int(datetime.now(UTC).timestamp())
        rows: list[dict[str, Any]] = []
        skip = 0
        while True:
            data = await self._graphql(
                MARKETS_QUERY,
                {"maturityGte": str(maturity_gte), "skip": skip},
            )
            batch = data.get("markets") or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < 1000:
                break
            skip += 1000
        return rows

    async def fetch_market_quotes(self) -> list[MarketQuote]:
        rows = await self.fetch_open_market_rows()
        quotes: list[MarketQuote] = []

        # Group metadata per (game_id, market_type) for sport/league labels
        for row in rows:
            game_id = _decode_game_id(str(row["gameId"]))
            type_id = int(row["typeId"])
            line = int(row["line"])
            player_id = int(row["playerId"])
            market_type = _market_type_key(type_id, line, player_id)
            side_index = int(row["position"])
            odd_raw = float(row["odd"])
            implied = _odd_to_implied(row["odd"])
            if implied <= 0 or implied >= 1:
                continue
            kickoff = datetime.fromtimestamp(int(row["maturity"]), tz=UTC)
            sport_id = int(row["sportId"])
            sport = f"sport_{sport_id}"
            status = int(row["status"])

            pseudo_market = {
                "homeTeam": "home",
                "awayTeam": "away",
                "isOneSideMarket": False,
            }
            quotes.append(
                MarketQuote(
                    chain=self.chain_name,
                    chain_id=self.chain_id,
                    game_id=game_id,
                    market_type=market_type,
                    market_type_id=type_id,
                    side_index=side_index,
                    side_label=_side_label(pseudo_market, side_index),
                    implied_prob=implied,
                    decimal_odds=1.0 / implied if implied > 0 else 0.0,
                    liquidity_usd=None,
                    sport=sport,
                    league=f"type_{type_id}",
                    kickoff=kickoff,
                    market_address=None,
                    sport_id=sport_id,
                    line=line,
                    player_id=player_id if player_id != 0 else None,
                    status=status,
                    odd_raw=odd_raw,
                    fixture_key=decode_fixture_key(game_id),
                    subgraph_market_id=str(row.get("id") or ""),
                    raw=row,
                )
            )

        log.info(
            "subgraph_quotes_fetched",
            chain=self.chain_name,
            rows=len(rows),
            quotes=len(quotes),
        )
        return quotes

    async def fetch_recent_tickets(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent ticket rows with one dict per market leg."""
        data = await self._graphql(TICKETS_QUERY, {"first": limit})
        legs: list[dict[str, Any]] = []
        for ticket in data.get("tickets") or []:
            ticket_ts = datetime.fromtimestamp(int(ticket["timestamp"]), tz=UTC)
            for market in ticket.get("markets") or []:
                game_id = _decode_game_id(str(market["gameId"]))
                odd_raw = float(market["odd"]) if market.get("odd") is not None else None
                implied = _odd_to_implied(market["odd"]) if odd_raw else None
                legs.append(
                    {
                        "chain": self.chain_name,
                        "ticket_id": str(ticket["id"]),
                        "tx_hash": ticket.get("txHash"),
                        "ticket_ts": ticket_ts,
                        "buy_in_amount": _scaled_amount(ticket.get("buyInAmount"), ticket.get("collateral")),
                        "payout": _scaled_amount(ticket.get("payout"), ticket.get("collateral")),
                        "fees": _scaled_amount(ticket.get("fees"), ticket.get("collateral")),
                        "is_live": bool(ticket.get("isLive")),
                        "collateral": ticket.get("collateral"),
                        "game_id": game_id,
                        "fixture_key": decode_fixture_key(game_id),
                        "type_id": int(market["typeId"]),
                        "line": int(market["line"]),
                        "player_id": int(market["playerId"]) or None,
                        "position": int(market["position"]),
                        "odd_raw": odd_raw,
                        "implied_prob": implied,
                    }
                )
        log.info(
            "subgraph_tickets_fetched",
            chain=self.chain_name,
            tickets=len(data.get("tickets") or []),
            legs=len(legs),
        )
        return legs
