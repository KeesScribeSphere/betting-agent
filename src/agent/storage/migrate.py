"""Lightweight SQLite schema migrations for existing detection databases."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _columns(engine: Engine, table: str) -> set[str]:
    insp = inspect(engine)
    return {c["name"] for c in insp.get_columns(table)}


def migrate_detection_schema(engine: Engine) -> None:
    """Add new analytics columns/tables without losing existing Phase 2 data."""
    quote_additions = {
        "kickoff_ts": "DATETIME",
        "type_id": "INTEGER",
        "line": "INTEGER",
        "player_id": "INTEGER",
        "sport_id": "INTEGER",
        "status": "INTEGER",
        "decimal_odds": "FLOAT",
        "odd_raw": "FLOAT",
        "fixture_key": "VARCHAR(64)",
        "subgraph_market_id": "VARCHAR(256)",
        "minutes_to_kickoff": "FLOAT",
        "chain_id": "INTEGER",
    }
    gap_additions = {
        "kickoff_ts": "DATETIME",
        "sport_id": "INTEGER",
        "type_id": "INTEGER",
        "line": "INTEGER",
        "fixture_key": "VARCHAR(64)",
    }

    with engine.begin() as conn:
        existing = _columns(engine, "quote_snapshots") if "quote_snapshots" in inspect(engine).get_table_names() else set()
        for col, sql_type in quote_additions.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE quote_snapshots ADD COLUMN {col} {sql_type}"))

        if "cross_chain_gaps" in inspect(engine).get_table_names():
            gap_cols = _columns(engine, "cross_chain_gaps")
            for col, sql_type in gap_additions.items():
                if col not in gap_cols:
                    conn.execute(text(f"ALTER TABLE cross_chain_gaps ADD COLUMN {col} {sql_type}"))
