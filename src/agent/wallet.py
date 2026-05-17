"""EOA wallet loading and per-chain balance checks."""

from __future__ import annotations

from eth_account import Account

from agent.config import AppConfig, EnvSettings
from agent.exchange.overtime.contracts import OvertimeContracts
from agent.logging_setup import get_logger

log = get_logger(__name__)


class WalletService:
    def __init__(self, config: AppConfig, env: EnvSettings, require_key: bool = False) -> None:
        self.config = config
        self.env = env
        self._private_key: str | None = None
        self._address: str | None = None

        if require_key or env.agent_private_key:
            self._private_key = env.require_private_key() if require_key else env.agent_private_key
            if self._private_key:
                self._address = Account.from_key(self._private_key).address

        self._contracts = {
            name: OvertimeContracts(
                rpc_urls=chain.rpc_urls,
                chain_id=chain.chain_id,
                sports_amm_address=chain.sports_amm_v2,
                usdc_address=chain.usdc,
                private_key=self._private_key,
            )
            for name, chain in config.chains.items()
        }

    @property
    def address(self) -> str | None:
        return self._address

    async def get_all_balances(self) -> dict[str, dict[str, float]]:
        if not self._address:
            return {name: {"eth": 0.0, "usdc": 0.0} for name in self.config.chains}
        out: dict[str, dict[str, float]] = {}
        for name, contracts in self._contracts.items():
            eth_wei = await contracts.get_eth_balance(self._address)
            usdc_raw = await contracts.get_usdc_balance(self._address)
            out[name] = {"eth": eth_wei / 10**18, "usdc": usdc_raw / 10**6}
        return out

    async def validate_live_startup(self) -> None:
        if not self._private_key or not self._address:
            raise RuntimeError("AGENT_PRIVATE_KEY required for live mode")

        balances = await self.get_all_balances()
        total_usdc = sum(b["usdc"] for b in balances.values())
        if total_usdc > self.config.risk.max_bankroll_usdc * 1.05:
            raise RuntimeError(
                f"Total USDC {total_usdc:.2f} exceeds max_bankroll "
                f"{self.config.risk.max_bankroll_usdc}"
            )

        for chain, bal in balances.items():
            if bal["eth"] < self.config.risk.min_gas_eth:
                raise RuntimeError(f"Insufficient gas on {chain}: {bal['eth']} ETH")
        log.info("wallet_validation_ok", address=self._address, total_usdc=total_usdc)
