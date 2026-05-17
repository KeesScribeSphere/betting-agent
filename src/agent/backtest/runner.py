"""Replay detection DB with simulated cross-chain execution."""

from __future__ import annotations

import random
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from agent.config import AppConfig, load_config
from agent.logging_setup import configure_logging, get_logger
from agent.storage.models import Base, CrossChainGap, PlacedBet
from agent.storage.repo import Repository

log = get_logger(__name__)


class BacktestRunner:
    def __init__(
        self,
        config: AppConfig,
        source_db: str,
        output_db: str,
        leg2_failure_rate: float = 0.05,
        rpc_error_rate: float = 0.01,
    ) -> None:
        self.config = config
        self.source_db = source_db
        self.output_db = output_db
        self.leg2_failure_rate = leg2_failure_rate
        self.rpc_error_rate = rpc_error_rate
        self._source = create_engine(f"sqlite:///{source_db}")
        self._out_repo = Repository(output_db)

    def run(self) -> dict[str, float]:
        threshold = self.config.cost_floor.threshold_pct
        SessionLocal = sessionmaker(bind=self._source)
        simulated_pnl = 0.0
        trades = 0
        wins = 0

        with SessionLocal() as session:
            gaps = session.execute(
                select(CrossChainGap).where(CrossChainGap.net_gap_pct >= threshold)
            ).scalars().all()

        for gap in gaps:
            if random.random() < self.rpc_error_rate:
                continue
            stake = min(self.config.risk.per_trade_usdc_cap, 5.0)
            cost_pct = (
                self.config.cost_floor.overtime_fee_pct_per_leg * 2
                + self.config.cost_floor.slippage_pct_per_leg * 2
            ) / 100
            gross = stake * (gap.net_gap_pct / 100)
            costs = stake * cost_pct
            if random.random() < self.leg2_failure_rate:
                pnl = -stake * 0.5
            else:
                pnl = gross - costs
                wins += 1
            simulated_pnl += pnl
            trades += 1
            arb_id = str(uuid.uuid4())[:8]
            self._out_repo.record_bet(
                PlacedBet(
                    game_id=gap.game_id,
                    market_type=gap.market_type,
                    chain=gap.chain_a,
                    side_index=gap.side_index,
                    stake_usdc=stake,
                    simulated=True,
                    leg=1,
                    arb_group_id=arb_id,
                )
            )

        self._out_repo.upsert_daily_summary(
            gaps_acted=trades,
            pnl_delta=simulated_pnl,
            simulated=True,
        )
        log.info(
            "backtest_complete",
            trades=trades,
            wins=wins,
            simulated_pnl=round(simulated_pnl, 2),
        )
        return {"trades": trades, "wins": wins, "simulated_pnl": simulated_pnl}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Backtest from detection SQLite DB")
    parser.add_argument("--source-db", default="data/agent.db")
    parser.add_argument("--output-db", default="data/backtest.db")
    args = parser.parse_args()
    config = load_config()
    configure_logging(config.agent.log_path)
    runner = BacktestRunner(config, args.source_db, args.output_db)
    runner.run()
