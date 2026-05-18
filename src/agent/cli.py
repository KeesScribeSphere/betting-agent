"""CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import sys

from agent.config import load_config, load_env
from agent.live.runner import run_async
from agent.logging_setup import configure_logging, get_logger

log = get_logger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="overtime-agent",
        description="Overtime cross-chain skew arbitrage agent",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect", help="Run detection-only monitor (Phase 2)")
    detect.add_argument("--once", action="store_true", help="Single poll then exit")

    sub.add_parser("paper", help="Run paper trading mode (Phase 4)")
    sub.add_parser("live", help="Run live trading (requires AGENT_LIVE=1)")
    sub.add_parser("backtest", help="Replay detection DB with simulated fills")

    smoke = sub.add_parser("smoke", help="Connectivity smoke test (API + RPC)")
    smoke.add_argument("--chain", default="base")

    dry = sub.add_parser("dry-run-quote", help="On-chain tradeQuote dry-run for one open market")
    dry.add_argument("--chain", default="base")
    dry.add_argument("--stake", type=float, default=5.0)

    args = parser.parse_args(argv)
    config = load_config()
    env = load_env()
    configure_logging(config.agent.log_path)

    if args.command == "detect":
        if args.once:
            asyncio.run(_detect_once(config, env))
        else:
            asyncio.run(run_async("detection"))
    elif args.command == "paper":
        asyncio.run(run_async("paper"))
    elif args.command == "live":
        asyncio.run(run_async("live"))
    elif args.command == "backtest":
        from agent.backtest.runner import main as backtest_main

        backtest_main()
    elif args.command == "smoke":
        asyncio.run(_smoke_test(config, env, args.chain))
    elif args.command == "dry-run-quote":
        asyncio.run(_dry_run_quote(config, env, args.chain, args.stake))
    else:
        parser.print_help()
        sys.exit(1)


async def _detect_once(config, env) -> None:
    from agent.detection.monitor import DetectionMonitor
    from agent.storage.repo import Repository

    monitor = DetectionMonitor(config, env, Repository(config.agent.db_path))
    try:
        stats = await monitor.poll_once()
        log.info("detect_once_complete", **stats)
    finally:
        await monitor.close()


async def _dry_run_quote(config, env, chain_name: str, stake: float) -> None:
    from agent.exchange.base import TradeRequest
    from agent.exchange.overtime.adapter import OvertimeAdapter

    chain = config.chains.get(chain_name)
    if not chain:
        raise SystemExit(f"Unknown chain: {chain_name}")

    adapter = OvertimeAdapter(
        chain_config=chain,
        api_config=config.overtime_api,
        execution_config=config.execution.model_copy(update={"mode": "onchain"}),
        api_key=env.overtime_api_key,
        graph_api_key=env.thegraph_api_key,
        simulate_trades=True,
    )
    try:
        quotes = await adapter.fetch_market_quotes()
        if not quotes:
            raise SystemExit("No open quotes")
        q = quotes[0]
        req = TradeRequest(
            game_id=q.game_id,
            market_type=q.market_type,
            side_index=q.side_index,
            stake_usdc=stake,
            type_id=q.market_type_id,
            line=q.line or 0,
            player_id=q.player_id or 0,
            sport_id=q.sport_id or 0,
        )
        quote = await adapter.get_quote(req)
        log.info("dry_run_quote_ok", chain=chain_name, quote=quote)
    finally:
        await adapter.close()


async def _smoke_test(config, env, chain_name: str) -> None:
    from agent.exchange.overtime.adapter import OvertimeAdapter
    from agent.wallet import WalletService

    chain = config.chains.get(chain_name)
    if not chain:
        raise SystemExit(f"Unknown chain: {chain_name}")

    adapter = OvertimeAdapter(
        chain_config=chain,
        api_config=config.overtime_api,
        execution_config=config.execution,
        api_key=env.overtime_api_key,
        graph_api_key=env.thegraph_api_key,
        simulate_trades=True,
    )
    try:
        quotes = await adapter.fetch_market_quotes()
        log.info(
            "smoke_quotes_ok",
            chain=chain_name,
            quote_count=len(quotes),
            data_source=config.overtime_api.data_source,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("smoke_quotes_failed", chain=chain_name, error=str(exc))

    wallet = WalletService(config, env)
    try:
        if wallet.address:
            bal = await wallet.get_all_balances()
            log.info("smoke_rpc_ok", balances=bal)
        else:
            from web3 import AsyncWeb3
            from web3.providers import AsyncHTTPProvider

            connected = False
            for url in chain.rpc_urls:
                w3 = AsyncWeb3(AsyncHTTPProvider(url))
                try:
                    if await w3.is_connected():
                        block = await w3.eth.block_number
                        log.info("smoke_rpc_ok", chain=chain_name, rpc=url, block=block)
                        connected = True
                        break
                finally:
                    provider = w3.provider
                    if hasattr(provider, "disconnect"):
                        await provider.disconnect()
            if not connected:
                log.error("smoke_rpc_failed", chain=chain_name)
    except Exception as exc:  # noqa: BLE001
        log.error("smoke_rpc_failed", chain=chain_name, error=str(exc))
    finally:
        await adapter.close()


if __name__ == "__main__":
    main()
