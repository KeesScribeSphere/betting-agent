"""Thin repository over SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from agent.storage.migrate import migrate_detection_schema
from agent.storage.models import (
    Base,
    BridgeOperation,
    CrossChainGap,
    DailyPnL,
    KillSwitchEvent,
    PlacedBet,
    QuoteSnapshot,
    TicketEvent,
)


class Repository:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)

        @event.listens_for(self._engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        with self._engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=30000"))
            conn.commit()

        Base.metadata.create_all(self._engine)
        migrate_detection_schema(self._engine)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._session_factory()

    def add_quote_snapshots(self, snapshots: Iterable[QuoteSnapshot]) -> int:
        with self.session() as session:
            items = list(snapshots)
            session.add_all(items)
            session.commit()
            return len(items)

    def add_ticket_events(self, events: Iterable[TicketEvent]) -> int:
        items = list(events)
        if not items:
            return 0
        keys = {(e.chain, e.ticket_id, e.game_id, e.position) for e in items}
        with self.session() as session:
            existing = session.execute(
                select(TicketEvent.chain, TicketEvent.ticket_id, TicketEvent.game_id, TicketEvent.position).where(
                    TicketEvent.chain.in_({k[0] for k in keys}),
                    TicketEvent.ticket_id.in_({k[1] for k in keys}),
                )
            ).all()
            existing_keys = set(existing)
            new_items = [e for e in items if (e.chain, e.ticket_id, e.game_id, e.position) not in existing_keys]
            if not new_items:
                return 0
            session.add_all(new_items)
            session.commit()
            return len(new_items)

    def add_gaps(self, gaps: Iterable[CrossChainGap]) -> int:
        with self.session() as session:
            items = list(gaps)
            session.add_all(items)
            session.commit()
            return len(items)

    def record_bet(self, bet: PlacedBet) -> PlacedBet:
        with self.session() as session:
            session.add(bet)
            session.commit()
            session.refresh(bet)
            return bet

    def record_bridge(self, op: BridgeOperation) -> BridgeOperation:
        with self.session() as session:
            session.add(op)
            session.commit()
            session.refresh(op)
            return op

    def trip_kill_switch(self, reason: str) -> None:
        with self.session() as session:
            session.add(KillSwitchEvent(reason=reason, active=True))
            session.commit()

    def daily_loss_usdc(self, day: date | None = None) -> float:
        day_str = (day or datetime.now(UTC).date()).isoformat()
        with self.session() as session:
            row = session.execute(
                select(DailyPnL.realized_pnl_usdc).where(DailyPnL.day == day_str)
            ).scalar_one_or_none()
            return float(row or 0.0)

    def upsert_daily_summary(
        self,
        gaps_seen: int = 0,
        gaps_acted: int = 0,
        pnl_delta: float = 0.0,
        simulated: bool = False,
    ) -> None:
        day_str = datetime.now(UTC).date().isoformat()
        with self.session() as session:
            row = session.execute(select(DailyPnL).where(DailyPnL.day == day_str)).scalar_one_or_none()
            if row is None:
                row = DailyPnL(
                    day=day_str,
                    gaps_seen=0,
                    gaps_acted=0,
                    realized_pnl_usdc=0.0,
                    simulated_pnl_usdc=0.0,
                )
                session.add(row)
            row.gaps_seen = (row.gaps_seen or 0) + gaps_seen
            row.gaps_acted = (row.gaps_acted or 0) + gaps_acted
            if simulated:
                row.simulated_pnl_usdc = (row.simulated_pnl_usdc or 0.0) + pnl_delta
            else:
                row.realized_pnl_usdc = (row.realized_pnl_usdc or 0.0) + pnl_delta
            session.commit()

    def count_snapshots(self) -> int:
        with self.session() as session:
            return session.scalar(select(func.count()).select_from(QuoteSnapshot)) or 0

    def count_gaps_above(self, threshold_pct: float) -> int:
        with self.session() as session:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(CrossChainGap)
                    .where(CrossChainGap.net_gap_pct >= threshold_pct)
                )
                or 0
            )
