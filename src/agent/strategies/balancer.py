"""Cross-chain USDC rebalancing via Across."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from agent.config import AppConfig
from agent.logging_setup import get_logger
from agent.storage.models import BridgeOperation
from agent.storage.repo import Repository
from agent.wallet import WalletService

log = get_logger(__name__)


class CapitalBalancer:
    def __init__(
        self,
        config: AppConfig,
        wallet: WalletService,
        repo: Repository,
    ) -> None:
        self.config = config
        self.wallet = wallet
        self.repo = repo
        self._bridges_today = 0
        self._day = datetime.now(UTC).date()

    def _reset_daily_counter(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._day:
            self._day = today
            self._bridges_today = 0

    async def maybe_rebalance(self) -> BridgeOperation | None:
        self._reset_daily_counter()
        if self._bridges_today >= self.config.risk.max_bridges_per_day:
            return None

        balances = await self.wallet.get_all_balances()
        min_bal = self.config.risk.min_chain_balance_usd
        needy = [c for c, b in balances.items() if b["usdc"] < min_bal]
        if not needy:
            return None

        funded = max(balances.items(), key=lambda x: x[1]["usdc"])
        target_chain = needy[0]
        amount = min(30.0, funded[1]["usdc"] - min_bal)
        if amount <= 0:
            return None

        op = await self._bridge_usdc(funded[0], target_chain, amount)
        if op:
            self._bridges_today += 1
        return op

    async def _bridge_usdc(self, from_chain: str, to_chain: str, amount: float) -> BridgeOperation | None:
        """Request Across route; live signing deferred to wallet integration."""
        log.info("bridge_requested", from_chain=from_chain, to_chain=to_chain, amount=amount)
        op = BridgeOperation(
            from_chain=from_chain,
            to_chain=to_chain,
            amount_usdc=amount,
            status="requested",
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Across suggested-fees endpoint (public)
                from_cfg = self.config.chains[from_chain]
                to_cfg = self.config.chains[to_chain]
                params = {
                    "originChainId": from_cfg.chain_id,
                    "destinationChainId": to_cfg.chain_id,
                    "token": from_cfg.usdc,
                    "amount": str(int(amount * 10**6)),
                }
                resp = await client.get(
                    f"{self.config.across.api_url}/suggested-fees",
                    params=params,
                )
                if resp.is_success:
                    data = resp.json()
                    op.fee_usd = float(data.get("totalRelayFee", {}).get("total", 0) or 0)
                    op.status = "quoted"
        except Exception as exc:  # noqa: BLE001
            log.warning("across_quote_failed", error=str(exc))
            op.status = "quote_failed"

        return self.repo.record_bridge(op)
