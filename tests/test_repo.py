import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from sqlalchemy import inspect

from agent.storage.models import DailyPnL, QuoteSnapshot, TicketEvent
from agent.storage.repo import Repository


def test_upsert_daily_summary_new_row():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(str(Path(tmp) / "t.db"))
        repo.upsert_daily_summary(gaps_seen=5)
        repo.upsert_daily_summary(gaps_seen=3)
        day_str = datetime.now(UTC).date().isoformat()
        with repo.session() as session:
            row = session.execute(select(DailyPnL).where(DailyPnL.day == day_str)).scalar_one()
            assert row.gaps_seen == 8


def test_repo_migrates_quote_analytics_columns():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(str(Path(tmp) / "t.db"))
        cols = {c["name"] for c in inspect(repo._engine).get_columns("quote_snapshots")}
        assert "fixture_key" in cols
        assert "kickoff_ts" in cols
        assert "ticket_events" in inspect(repo._engine).get_table_names()


def test_ticket_events_deduped():
    from datetime import UTC, datetime

    with tempfile.TemporaryDirectory() as tmp:
        repo = Repository(str(Path(tmp) / "t.db"))
        ts = datetime.now(UTC)
        event = TicketEvent(
            sampled_ts=ts,
            chain="base",
            ticket_id="t1",
            ticket_ts=ts,
            game_id="0x1",
            position=0,
        )
        assert repo.add_ticket_events([event]) == 1
        assert repo.add_ticket_events([event]) == 0
