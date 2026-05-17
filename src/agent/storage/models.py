"""SQLAlchemy persistence models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class MarketRecord(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    market_type: Mapped[str] = mapped_column(String(64), index=True)
    sport: Mapped[str] = mapped_column(String(64), default="unknown")
    league: Mapped[str] = mapped_column(String(128), default="unknown")
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    base_market_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    optimism_market_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    arbitrum_market_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class QuoteSnapshot(Base):
    __tablename__ = "quote_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    market_type: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(32), index=True)
    side_index: Mapped[int] = mapped_column(Integer)
    side_label: Mapped[str] = mapped_column(String(128))
    implied_prob: Mapped[float] = mapped_column(Float)
    liquidity_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sport: Mapped[str] = mapped_column(String(64))
    league: Mapped[str] = mapped_column(String(128))


class CrossChainGap(Base):
    __tablename__ = "cross_chain_gaps"
    __table_args__ = (
        UniqueConstraint("ts", "game_id", "market_type", "chain_a", "chain_b", "side_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    market_type: Mapped[str] = mapped_column(String(64), index=True)
    sport: Mapped[str] = mapped_column(String(64))
    league: Mapped[str] = mapped_column(String(128))
    chain_a: Mapped[str] = mapped_column(String(32))
    chain_b: Mapped[str] = mapped_column(String(32))
    side_index: Mapped[int] = mapped_column(Integer)
    prob_a: Mapped[float] = mapped_column(Float)
    prob_b: Mapped[float] = mapped_column(Float)
    gap_pct: Mapped[float] = mapped_column(Float)
    net_gap_pct: Mapped[float] = mapped_column(Float)


class PlacedBet(Base):
    __tablename__ = "placed_bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    market_type: Mapped[str] = mapped_column(String(64))
    chain: Mapped[str] = mapped_column(String(32))
    side_index: Mapped[int] = mapped_column(Integer)
    stake_usdc: Mapped[float] = mapped_column(Float)
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    leg: Mapped[int] = mapped_column(Integer, default=1)
    arb_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bet_id: Mapped[int] = mapped_column(Integer, index=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    pnl_usdc: Mapped[float] = mapped_column(Float)
    won: Mapped[bool] = mapped_column(Boolean)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(128), index=True)
    market_type: Mapped[str] = mapped_column(String(64))
    chain: Mapped[str] = mapped_column(String(32))
    side_index: Mapped[int] = mapped_column(Integer)
    exposure_usdc: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DailyPnL(Base):
    __tablename__ = "daily_pnl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    realized_pnl_usdc: Mapped[float] = mapped_column(Float, default=0.0)
    simulated_pnl_usdc: Mapped[float] = mapped_column(Float, default=0.0)
    gaps_seen: Mapped[int] = mapped_column(Integer, default=0)
    gaps_acted: Mapped[int] = mapped_column(Integer, default=0)


class KillSwitchEvent(Base):
    __tablename__ = "kill_switch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    reason: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class BridgeOperation(Base):
    __tablename__ = "bridge_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    from_chain: Mapped[str] = mapped_column(String(32))
    to_chain: Mapped[str] = mapped_column(String(32))
    amount_usdc: Mapped[float] = mapped_column(Float)
    fee_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_tx: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dest_tx: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
