"""Overtime REST API client (V2 primary, V1-compatible paths where available)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from agent.exchange.base import MarketQuote
from agent.logging_setup import get_logger

log = get_logger(__name__)


def _parse_kickoff(market: dict[str, Any]) -> datetime | None:
    if market.get("maturityDate"):
        try:
            return datetime.fromisoformat(str(market["maturityDate"]).replace("Z", "+00:00"))
        except ValueError:
            pass
    maturity = market.get("maturity")
    if maturity:
        return datetime.fromtimestamp(int(maturity), tz=UTC)
    return None


def _side_label(market: dict[str, Any], index: int) -> str:
    if market.get("isOneSideMarket"):
        return "yes" if index == 0 else f"side_{index}"
    home = market.get("homeTeam", "home")
    away = market.get("awayTeam", "away")
    labels = [home, away, "draw"]
    if index < len(labels):
        return str(labels[index])
    return f"side_{index}"


def _market_type_name(market: dict[str, Any]) -> str:
    return str(market.get("type") or market.get("marketType") or f"type_{market.get('typeId', 0)}")


def market_to_quotes(chain: str, chain_id: int, market: dict[str, Any]) -> list[MarketQuote]:
    """Convert a single Overtime market dict to per-side quotes."""
    if not market.get("isOpen", True):
        return []

    game_id = str(market.get("gameId", ""))
    if not game_id:
        return []

    odds_list = market.get("odds") or []
    quotes: list[MarketQuote] = []
    kickoff = _parse_kickoff(market)
    market_type = _market_type_name(market)
    type_id = int(market.get("typeId", 0))
    sport = str(market.get("sport", "unknown"))
    league = str(market.get("leagueName", market.get("league", "unknown")))
    liquidity = market.get("liquidity")
    liquidity_usd = float(liquidity) if liquidity is not None else None
    market_address = market.get("address") or market.get("marketAddress")

    for idx, odds in enumerate(odds_list):
        if not isinstance(odds, dict):
            continue
        implied = odds.get("normalizedImplied")
        if implied is None and odds.get("decimal"):
            implied = 1.0 / float(odds["decimal"])
        if implied is None:
            continue
        quotes.append(
            MarketQuote(
                chain=chain,
                chain_id=chain_id,
                game_id=game_id,
                market_type=market_type,
                market_type_id=type_id,
                side_index=idx,
                side_label=_side_label(market, idx),
                implied_prob=float(implied),
                decimal_odds=float(odds.get("decimal", 0) or 0),
                liquidity_usd=liquidity_usd,
                sport=sport,
                league=league,
                kickoff=kickoff,
                market_address=str(market_address) if market_address else None,
                raw=market,
            )
        )

    for child in market.get("childMarkets") or []:
        if isinstance(child, dict):
            quotes.extend(market_to_quotes(chain, chain_id, child))

    return quotes


def normalize_markets_payload(data: Any) -> list[dict[str, Any]]:
    """Normalize API response into a flat list of market dicts."""
    if isinstance(data, dict):
        if data.get("markets") == "no change":
            return []
        markets = data.get("markets")
        if isinstance(markets, dict):
            if "gameId" in markets:
                return [markets]
            return [m for m in markets.values() if isinstance(m, dict)]
        if isinstance(markets, list):
            return [m for m in markets if isinstance(m, dict)]
    if isinstance(data, list):
        return [m for m in data if isinstance(m, dict)]
    return []


class OvertimeRestClient:
    """HTTP client for Overtime markets and quotes."""

    def __init__(
        self,
        base_url: str,
        chain_id: int,
        chain_name: str,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.chain_id = chain_id
        self.chain_name = chain_name
        self.api_key = api_key
        self._response_hash: str | None = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_markets(self) -> list[dict[str, Any]]:
        """Fetch markets for this chain (V2 endpoint)."""
        params: dict[str, str] = {
            "onlyBasicProperties": "true",
            "includeHashInResponse": "true",
        }
        if self._response_hash:
            params["responseHash"] = self._response_hash

        url = f"/overtime-v2/networks/{self.chain_id}/markets"
        resp = await self._client.get(url, params=params)
        if resp.status_code == 401:
            log.warning(
                "overtime_api_unauthorized",
                chain=self.chain_name,
                hint="Set OVERTIME_API_KEY in .env",
            )
            resp.raise_for_status()
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("responseHash"):
            self._response_hash = str(data["responseHash"])
        return normalize_markets_payload(data)

    async def fetch_quotes(self, game_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        url = f"/overtime-v2/networks/{self.chain_id}/quote"
        resp = await self._client.post(url, json=request_body)
        resp.raise_for_status()
        return resp.json()

    async def fetch_user_history(self, user_address: str) -> dict[str, Any]:
        url = f"/overtime-v2/networks/{self.chain_id}/users/{user_address}/history"
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def fetch_market_quotes(self) -> list[MarketQuote]:
        markets = await self.fetch_markets()
        quotes: list[MarketQuote] = []
        for market in markets:
            quotes.extend(market_to_quotes(self.chain_name, self.chain_id, market))
        return quotes
