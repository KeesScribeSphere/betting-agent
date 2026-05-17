from datetime import UTC, datetime, timedelta

from agent.detection.monitor import DetectionMonitor
from agent.exchange.base import MarketQuote


def _minimal_config():
    from agent.config import AgentConfig, AppConfig, CostFloorConfig

    return AppConfig(
        agent=AgentConfig(),
        cost_floor=CostFloorConfig(),
        chains={},
    )


def test_snapshot_from_quote_populates_analytics_fields():
    monitor = DetectionMonitor(config=_minimal_config(), env=None, repo=None)  # type: ignore[arg-type]
    ts = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    kickoff = ts + timedelta(hours=2)
    q = MarketQuote(
        chain="base",
        chain_id=8453,
        game_id="0x3230323630353137413243314541350000000000000000000000000000000000",
        market_type="type_11038_line_250",
        market_type_id=11038,
        side_index=0,
        side_label="home",
        implied_prob=0.45,
        decimal_odds=2.22,
        liquidity_usd=None,
        sport="sport_1",
        league="type_11038",
        kickoff=kickoff,
        market_address=None,
        sport_id=1,
        line=250,
        player_id=None,
        status=0,
        odd_raw=4.5e17,
        fixture_key="20260517A2C1EA5",
        subgraph_market_id="0xabc",
    )
    snap = monitor._snapshot_from_quote(ts, q)
    assert snap.fixture_key == "20260517A2C1EA5"
    assert snap.type_id == 11038
    assert snap.line == 250
    assert snap.minutes_to_kickoff == 120.0
    assert snap.decimal_odds == 2.22
