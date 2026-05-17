#!/usr/bin/env python3
"""Phase 2 decision gate analysis (run after 14-21 days of detection)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/agent.db")
    parser.add_argument("--threshold", type=float, default=6.0)
    args = parser.parse_args()

    engine = create_engine(f"sqlite:///{args.db}")
    gaps = pd.read_sql(
        text(
            "SELECT date(ts) as day, net_gap_pct, gap_pct, sport, league, market_type, chain_a, chain_b "
            "FROM cross_chain_gaps"
        ),
        engine,
    )
    if gaps.empty:
        print("CONCLUDE_PROJECT — no gap data in database")
        return

    gaps["actionable"] = gaps["net_gap_pct"] >= args.threshold
    daily = gaps.groupby("day")["actionable"].sum()
    median_actionable = daily.median() if len(daily) else 0

    print("=== Gap distribution ===")
    print(gaps["net_gap_pct"].describe())
    print("\n=== Actionable gaps per day (median) ===")
    print(f"median actionable/day: {median_actionable:.1f}")

    if median_actionable >= 3:
        print("\n>>> PROCEED_TO_LIVE <<<")
    else:
        print("\n>>> CONCLUDE_PROJECT <<<")


if __name__ == "__main__":
    main()
