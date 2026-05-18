"""Typed configuration loaded from YAML + environment."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from agent.util.addresses import checksum_address
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    poll_interval_seconds: int = 5
    db_path: str = "data/agent.db"
    kill_switch_path: str = "data/kill-switch.flag"
    log_path: str = "data/agent.jsonl"
    timezone: str = "Europe/Amsterdam"
    # Sample recent subgraph tickets every N polls (~60s at 5s interval when N=12)
    ticket_sampling_enabled: bool = True
    ticket_sample_every_n_polls: int = 12
    ticket_sample_limit: int = 100


class CostFloorConfig(BaseModel):
    min_edge_pct: float = 6.0
    safety_buffer_pct: float = 0.5
    overtime_fee_pct_per_leg: float = 2.0
    bridge_fee_pct: float = 0.04
    slippage_pct_per_leg: float = 0.75

    @property
    def threshold_pct(self) -> float:
        return self.min_edge_pct + self.safety_buffer_pct


class RiskConfig(BaseModel):
    max_bankroll_usdc: float = 200
    per_trade_usdc_cap: float = 5
    per_event_exposure_usdc: float = 20
    daily_loss_cap_usdc: float = 20
    min_chain_balance_usd: float = 20
    min_gas_eth: float = 0.0005
    max_bridges_per_day: int = 3
    max_orders_per_chain_per_minute: int = 10


class OvertimeApiConfig(BaseModel):
    base_url: str = "https://api.overtime.io"
    # detection: subgraph only (default). rest: REST only. auto: subgraph, REST fallback.
    data_source: str = "subgraph"


class ExecutionConfig(BaseModel):
    # rest: Overtime API only. onchain: merkle + tradeQuote/trade. auto: REST if key else onchain.
    mode: str = "auto"
    # eth_call tradeQuote before any tx (paper + live)
    dry_run_quote_onchain: bool = True


class AcrossConfig(BaseModel):
    api_url: str = "https://app.across.to/api"


class ChainConfig(BaseModel):
    chain_id: int
    name: str
    rpc_urls: list[str]
    sports_amm_v2: str
    usdc: str
    native_symbol: str = "ETH"

    @field_validator("sports_amm_v2", "usdc")
    @classmethod
    def _checksum_address(cls, v: str) -> str:
        return checksum_address(v)


class AppConfig(BaseModel):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    cost_floor: CostFloorConfig = Field(default_factory=CostFloorConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    overtime_api: OvertimeApiConfig = Field(default_factory=OvertimeApiConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    across: AcrossConfig = Field(default_factory=AcrossConfig)
    chains: dict[str, ChainConfig] = Field(default_factory=dict)

    def chain_by_id(self, chain_id: int) -> ChainConfig:
        for chain in self.chains.values():
            if chain.chain_id == chain_id:
                return chain
        raise KeyError(f"Unknown chain_id {chain_id}")

    def chain_names(self) -> list[str]:
        return list(self.chains.keys())


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    agent_private_key: str | None = Field(default=None, alias="AGENT_PRIVATE_KEY")
    overtime_api_key: str | None = Field(default=None, alias="OVERTIME_API_KEY")
    thegraph_api_key: str | None = Field(default=None, alias="THEGRAPH_API_KEY")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")
    paper_mode: bool = Field(default=False, alias="PAPER_MODE")
    agent_live: bool = Field(default=False, alias="AGENT_LIVE")

    def require_private_key(self) -> str:
        if not self.agent_private_key:
            raise RuntimeError("AGENT_PRIVATE_KEY is required for this mode")
        return self.agent_private_key


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.environ.get("AGENT_CONFIG", "config.yaml"))
    if not config_path.exists():
        example = Path("config.example.yaml")
        if example.exists():
            config_path = example
        else:
            return AppConfig()

    with config_path.open() as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    chains_raw = raw.get("chains", {})
    chains = {name: ChainConfig(**cfg) for name, cfg in chains_raw.items()}
    _prepend_env_rpc_urls(chains)
    raw["chains"] = chains
    return AppConfig(**raw)


def _prepend_env_rpc_urls(chains: dict[str, ChainConfig]) -> None:
    """Prefer private RPC URLs from env (avoids 429 on public endpoints)."""
    env_map = {
        "base": os.environ.get("BASE_RPC_URL"),
        "optimism": os.environ.get("OPTIMISM_RPC_URL"),
        "arbitrum": os.environ.get("ARBITRUM_RPC_URL"),
    }
    for name, url in env_map.items():
        if not url or name not in chains:
            continue
        chain = chains[name]
        rest = [u for u in chain.rpc_urls if u != url]
        chain.rpc_urls = [url, *rest]


def load_env() -> EnvSettings:
    return EnvSettings()
