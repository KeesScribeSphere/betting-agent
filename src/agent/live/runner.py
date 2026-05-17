"""Live / paper runner: detection + optional execution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from agent.alerts import Alerter, build_alerter
from agent.config import AppConfig, EnvSettings, load_config, load_env
from agent.detection.monitor import DetectionMonitor
from agent.exchange.overtime.adapter import OvertimeAdapter
from agent.logging_setup import configure_logging, get_logger
from agent.mapper.game_mapper import GameMapper
from agent.risk.manager import RiskManager
from agent.storage.repo import Repository
from agent.strategies.balancer import CapitalBalancer
from agent.strategies.cross_chain import CrossChainStrategy
from agent.strategies.leg_coordinator import LegCoordinator
from agent.wallet import WalletService

log = get_logger(__name__)


class LiveRunner:
    def __init__(
        self,
        config: AppConfig,
        env: EnvSettings,
        alerter: Alerter,
    ) -> None:
        self.config = config
        self.env = env
        self.alerter = alerter
        self.repo = Repository(config.agent.db_path)
        self.wallet = WalletService(config, env, require_key=env.agent_live)
        self.risk = RiskManager(config, self.repo)
        self.mapper = GameMapper()
        self.simulate = env.paper_mode or not env.agent_live

        self.adapters: dict[str, OvertimeAdapter] = {
            name: OvertimeAdapter(
                chain_config=chain_cfg,
                api_config=config.overtime_api,
                api_key=env.overtime_api_key,
                graph_api_key=env.thegraph_api_key,
                private_key=env.agent_private_key if env.agent_live else None,
                simulate_trades=self.simulate,
            )
            for name, chain_cfg in config.chains.items()
        }
        self.detection = DetectionMonitor(config, env, self.repo)
        self.detection.adapters = self.adapters
        self.legs = LegCoordinator(self.adapters, self.repo)
        self.strategy = CrossChainStrategy(config, self.risk, self.legs)
        self.balancer = CapitalBalancer(config, self.wallet, self.repo)

    async def close(self) -> None:
        await asyncio.gather(*(a.close() for a in self.adapters.values()))

    async def startup(self) -> None:
        if self.env.agent_live:
            await self.wallet.validate_live_startup()
            await self.alerter.send("Agent starting in LIVE mode", level="warning")
        elif self.simulate:
            await self.alerter.send("Agent starting in PAPER mode")
        else:
            await self.alerter.send("Agent starting in DETECTION mode")

    async def reconcile_positions(self) -> None:
        if not self.wallet.address:
            return
        for name, adapter in self.adapters.items():
            try:
                positions = await adapter.fetch_open_positions()
                log.info("reconcile_chain", chain=name, positions=len(positions))
            except Exception as exc:  # noqa: BLE001
                await self.alerter.send(f"Reconcile failed on {name}: {exc}", level="error")

    async def run_loop(self) -> None:
        await self.startup()
        interval = self.config.agent.poll_interval_seconds
        last_heartbeat = datetime.now(UTC)

        while not self.risk.is_kill_switch_active():
            try:
                stats = await self.detection.poll_once()
                quotes_by_chain = {}
                for name, adapter in self.adapters.items():
                    quotes_by_chain[name] = await adapter.fetch_market_quotes()

                if self.simulate or self.env.agent_live:
                    unified = self.mapper.group(quotes_by_chain)
                    signals = self.strategy.find_signals(unified)
                    balances = await self.wallet.get_all_balances()
                    total_usdc = sum(b["usdc"] for b in balances.values())

                    for signal in signals[:3]:
                        chain_bal = balances.get(signal.chain_skewed, {"usdc": 0, "eth": 0})
                        liq = None
                        market = unified.get((signal.game_id, signal.market_type))
                        if market:
                            st = market.chains[signal.chain_skewed].quotes_by_side.get(signal.side_index)
                            liq = st.liquidity_usd if st else None

                        decision = self.risk.check_trade(
                            chain=signal.chain_skewed,
                            stake_usdc=signal.stake_usdc,
                            game_id=signal.game_id,
                            liquidity_usd=liq,
                            total_bankroll_usdc=total_usdc,
                            chain_usdc_balance=chain_bal["usdc"],
                            chain_eth_balance=chain_bal["eth"],
                        )
                        if not decision.allowed:
                            log.info("trade_blocked", reason=decision.reason)
                            continue
                        ok = await self.strategy.execute_signal(signal)
                        if ok:
                            self.repo.upsert_daily_summary(gaps_acted=1)

                    if self.env.agent_live:
                        await self.balancer.maybe_rebalance()

                now = datetime.now(UTC)
                if (now - last_heartbeat).total_seconds() >= 6 * 3600:
                    await self.alerter.send(
                        f"Agent alive — snapshots={stats.get('snapshots', 0)} gaps={stats.get('gaps', 0)}"
                    )
                    last_heartbeat = now

            except Exception as exc:  # noqa: BLE001
                log.exception("run_loop_error", error=str(exc))
                await self.alerter.send(f"Run loop error: {exc}", level="error")

            await asyncio.sleep(interval)

        await self.alerter.send("Kill switch active — agent halted", level="warning")


async def run_async(mode: str | None = None) -> None:
    config = load_config()
    env = load_env()
    configure_logging(config.agent.log_path)

    if mode == "detection":
        env = env.model_copy(update={"paper_mode": False, "agent_live": False})
    elif mode == "paper":
        env = env.model_copy(update={"paper_mode": True, "agent_live": False})
    elif mode == "live":
        if not env.agent_live:
            raise RuntimeError("Set AGENT_LIVE=1 to run live mode")
        env = env.model_copy(update={"paper_mode": False, "agent_live": True})

    alerter = build_alerter(env)

    if mode == "detection" or (not env.paper_mode and not env.agent_live):
        monitor = DetectionMonitor(config, env, Repository(config.agent.db_path))
        try:
            await monitor.run_forever()
        finally:
            await monitor.close()
        return

    runner = LiveRunner(config, env, alerter)
    try:
        await runner.reconcile_positions()
        await runner.run_loop()
    finally:
        await runner.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["detection", "paper", "live", "backtest"],
        default=None,
    )
    args = parser.parse_args()

    if args.mode == "backtest":
        from agent.backtest.runner import main as backtest_main

        backtest_main()
        return

    asyncio.run(run_async(args.mode))
