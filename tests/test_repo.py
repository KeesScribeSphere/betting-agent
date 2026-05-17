import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from agent.storage.models import DailyPnL
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
