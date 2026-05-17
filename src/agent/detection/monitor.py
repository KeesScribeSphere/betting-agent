"""Detection-only monitor: poll quotes, persist gaps, zero capital."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from itertools import combinations

from agent.config import AppConfig, EnvSettings
from agent.exchange.base import MarketQuote
from agent.exchange.overtime.adapter import OvertimeAdapter
from agent.logging_setup import get_logger
from agent.mapper.game_mapper import GameMapper
from agent.storage.models import CrossChainGap, QuoteSnapshot, TicketEvent
from agent.storage.repo import Repository

log = get_logger(__name__)

CHAIN_PAIRS = [("base", "optimism"), ("base", "arbitrum"), ("optimism", "arbitrum")]


class DetectionMonitor:
    def __init__(
        self,
        config: AppConfig,
        env: EnvSettings,
        repo: Repository,
    ) -> None:
        self.config = config
        self.env = env
        self.repo = repo
        self.mapper = GameMapper()
        self._poll_count = 0
        self.adapters: dict[str, OvertimeAdapter] = {
            name: OvertimeAdapter(
                chain_config=chain_cfg,
                api_config=config.overtime_api,
                api_key=env.overtime_api_key,
                graph_api_key=env.thegraph_api_key,
                simulate_trades=True,
            )
            for name, chain_cfg in config.chains.items()
        }

    async def close(self) -> None:
        await asyncio.gather(*(a.close() for a in self.adapters.values()))

    def _snapshot_from_quote(self, ts: datetime, q: MarketQuote) -> QuoteSnapshot:
        minutes_to_kickoff = None
        if q.kickoff is not None:
            minutes_to_kickoff = (q.kickoff - ts).total_seconds() / 60.0
        return QuoteSnapshot(
            ts=ts,
            game_id=q.game_id,
            market_type=q.market_type,
            chain=q.chain,
            chain_id=q.chain_id,
            side_index=q.side_index,
            side_label=q.side_label,
            implied_prob=q.implied_prob,
            decimal_odds=q.decimal_odds,
            odd_raw=q.odd_raw,
            liquidity_usd=q.liquidity_usd,
            sport=q.sport,
            sport_id=q.sport_id,
            league=q.league,
            type_id=q.market_type_id,
            line=q.line,
            player_id=q.player_id,
            status=q.status,
            kickoff_ts=q.kickoff,
            minutes_to_kickoff=minutes_to_kickoff,
            fixture_key=q.fixture_key,
            subgraph_market_id=q.subgraph_market_id,
        )

    async def poll_once(self) -> dict[str, int]:
        self._poll_count += 1
        quotes_by_chain: dict[str, list] = {}
        tasks = {name: adapter.fetch_market_quotes() for name, adapter in self.adapters.items()}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for (name, _), result in zip(tasks.items(), results, strict=True):
            if isinstance(result, Exception):
                log.error("chain_poll_failed", chain=name, error=str(result))
                quotes_by_chain[name] = []
            else:
                quotes_by_chain[name] = result

        ts = datetime.now(UTC)
        snapshots: list[QuoteSnapshot] = []
        for quotes in quotes_by_chain.values():
            for q in quotes:
                snapshots.append(self._snapshot_from_quote(ts, q))

        snapshot_count = self.repo.add_quote_snapshots(snapshots) if snapshots else 0
        ticket_count = 0
        if self._should_sample_tickets():
            ticket_count = await self._sample_tickets(ts)
        unified = self.mapper.group(quotes_by_chain)
        gaps = self._compute_gaps(ts, unified)
        gap_count = self.repo.add_gaps(gaps) if gaps else 0

        if gaps:
            self.repo.upsert_daily_summary(gaps_seen=len(gaps))

        log.info(
            "detection_poll_complete",
            snapshots=snapshot_count,
            gaps=gap_count,
            markets=len(unified),
            ticket_events=ticket_count,
        )
        return {
            "snapshots": snapshot_count,
            "gaps": gap_count,
            "markets": len(unified),
            "ticket_events": ticket_count,
        }

    def _should_sample_tickets(self) -> bool:
        cfg = self.config.agent
        if not cfg.ticket_sampling_enabled:
            return False
        every = max(1, cfg.ticket_sample_every_n_polls)
        return self._poll_count % every == 0

    async def _sample_tickets(self, sampled_ts: datetime) -> int:
        limit = self.config.agent.ticket_sample_limit
        events: list[TicketEvent] = []
        tasks = {name: adapter.fetch_recent_tickets(limit=limit) for name, adapter in self.adapters.items()}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for (name, _), result in zip(tasks.items(), results, strict=True):
            if isinstance(result, Exception):
                log.warning("ticket_sample_failed", chain=name, error=str(result))
                continue
            for leg in result:
                events.append(
                    TicketEvent(
                        sampled_ts=sampled_ts,
                        chain=leg["chain"],
                        ticket_id=leg["ticket_id"],
                        tx_hash=leg.get("tx_hash"),
                        ticket_ts=leg["ticket_ts"],
                        buy_in_amount=leg.get("buy_in_amount"),
                        payout=leg.get("payout"),
                        fees=leg.get("fees"),
                        is_live=leg.get("is_live", False),
                        collateral=leg.get("collateral"),
                        game_id=leg["game_id"],
                        fixture_key=leg.get("fixture_key"),
                        type_id=leg.get("type_id"),
                        line=leg.get("line"),
                        player_id=leg.get("player_id"),
                        position=leg.get("position"),
                        odd_raw=leg.get("odd_raw"),
                        implied_prob=leg.get("implied_prob"),
                    )
                )
        return self.repo.add_ticket_events(events)

    def _compute_gaps(self, ts: datetime, unified: dict) -> list[CrossChainGap]:
        threshold = self.config.cost_floor.threshold_pct
        fee_legs = self.config.cost_floor.overtime_fee_pct_per_leg * 2
        slippage = self.config.cost_floor.slippage_pct_per_leg * 2
        cost_floor = fee_legs + slippage

        gaps: list[CrossChainGap] = []
        for market in unified.values():
            for chain_a, chain_b in market.chain_pairs():
                state_a = market.chains[chain_a]
                state_b = market.chains[chain_b]
                common_sides = set(state_a.quotes_by_side) & set(state_b.quotes_by_side)
                for side in common_sides:
                    qa = state_a.quotes_by_side[side]
                    qb = state_b.quotes_by_side[side]
                    gap_pct = abs(qa.implied_prob - qb.implied_prob) * 100
                    net_gap_pct = gap_pct - cost_floor
                    if gap_pct < 0.01:
                        continue
                    gaps.append(
                        CrossChainGap(
                            ts=ts,
                            game_id=market.game_id,
                            market_type=market.market_type,
                            sport=market.sport,
                            league=market.league,
                            chain_a=chain_a,
                            chain_b=chain_b,
                            side_index=side,
                            prob_a=qa.implied_prob,
                            prob_b=qb.implied_prob,
                            gap_pct=gap_pct,
                            net_gap_pct=net_gap_pct,
                            sport_id=qa.sport_id,
                            type_id=qa.market_type_id,
                            line=qa.line,
                            fixture_key=qa.fixture_key,
                            kickoff_ts=qa.kickoff,
                        )
                    )
                    if net_gap_pct >= threshold:
                        log.info(
                            "actionable_gap",
                            game_id=market.game_id,
                            market_type=market.market_type,
                            chain_a=chain_a,
                            chain_b=chain_b,
                            side=side,
                            net_gap_pct=round(net_gap_pct, 3),
                        )
        return gaps

    async def run_forever(self) -> None:
        interval = self.config.agent.poll_interval_seconds
        log.info("detection_monitor_started", interval=interval)
        while True:
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001
                log.exception("detection_poll_error", error=str(exc))
            await asyncio.sleep(interval)
