# Overtime Cross-Chain Skew Arbitrage Agent

Python agent for **cross-chain skew arbitrage** on [Overtime Markets](https://www.overtimemarkets.xyz/) across **Base**, **Optimism**, and **Arbitrum**.

This is a **learning project at ~$200 bankroll** with a binary empirical outcome: Phase 2 detection either shows enough cross-chain gaps above the ~5–6% cost floor (`PROCEED_TO_LIVE`) or the project stops (`CONCLUDE_PROJECT`).

## Modes

| Mode | CLI | Capital at risk |
|------|-----|-----------------|
| Detection | `python -m agent.cli detect` | None |
| Backtest | `python -m agent.cli backtest` | None (replay SQLite) |
| Paper | `python -m agent.cli paper` | Simulated |
| Live | `AGENT_LIVE=1 python -m agent.cli live` | Real |

## Quick start (local)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
cd OvertimeAgent
uv sync --extra dev
cp config.example.yaml config.yaml
cp .env.example .env
# Phase 2 detection: no OVERTIME_API_KEY needed (uses public subgraph).
# Live execution: OVERTIME_API_KEY still required (Overtime gates hobby projects).

uv run python -m agent.cli smoke --chain base
uv run python -m agent.cli detect --once
```

## Phase 0 checklist

Manual steps (see `wallet-setup.example.md`):

1. Dedicated EOA + seed backup (paper only, never in git)
2. Fund USDC + ETH on Base / Optimism / Arbitrum
3. Test bet on each chain via overtimemarkets.xyz
4. Across bridge test (OP → Base)
5. VPS hardened (`deploy/README.md`)
6. Telegram bot + chat ID in `.env` / `/etc/agent/env`
7. Rabby **watch-only** after live agent signs on VPS (not before)

## NL compliance

- Overtime ToS restricts OFAC jurisdictions only; Netherlands is not listed.
- No VPN — connect from NL residential IP.
- Agent auto-halts on sustained API/RPC failures; alerts via Telegram.

## Data sources (important)

| Need | Source | API key? |
|------|--------|----------|
| Phase 2 detection (quotes, gaps) | **SportsMarketsV2 subgraph** via The Graph | Optional `THEGRAPH_API_KEY` (free at thegraph.com/studio); defaults to the public key bundled with Overtime’s open-source `thales-data` |
| Live/paper trade quotes + tx payloads | Overtime REST `api.overtime.io` | **Yes** — `OVERTIME_API_KEY`, approval required; hobby projects are typically rejected |

**You can run the full 14–21 day detection phase without Overtime approving your REST API request.** If REST access is denied, the empirical answer from detection is still valid; automated live trading would require either API approval or additional on-chain engineering (merkle proofs for `trade()`).

Set `overtime_api.data_source: subgraph` in `config.yaml` (default).

## Config

- `config.yaml` — chains, RPCs, contract addresses, risk limits, cost floor, `overtime_api.data_source`
- `.env` — `AGENT_PRIVATE_KEY`, optional `OVERTIME_API_KEY`, optional `THEGRAPH_API_KEY`, `TELEGRAM_*`

Verify contract addresses at [contracts.overtime.io](https://contracts.overtime.io/).

## Phase 2 (detection run)

```bash
# Local or VPS
python -m agent.cli detect
# After 14-21 days:
python scripts/analyze_detection.py --db data/agent.db
```

Or use Jupyter: `notebooks/detection_analysis.ipynb`

**SQLite logging (Phase 2):**

- `quote_snapshots` — implied prob, decimal odds, `fixture_key`, kickoff, `type_id` / `line` / `sport_id`, subgraph market id
- `cross_chain_gaps` — same fixture metadata on each gap row
- `ticket_events` — recent on-chain tickets sampled from the subgraph (~every 60s by default)

Existing `data/agent.db` files are migrated in place on startup (new columns + `ticket_events` table). Weekly backup: `scripts/backup_detection_db.sh`.

## VPS deployment

See [deploy/README.md](deploy/README.md) for systemd units, logrotate, healthcheck cron, and emergency stop.

## Project structure

```
src/agent/
  exchange/overtime/   # REST + web3 adapter (per chain)
  mapper/              # game_id cross-chain grouping
  detection/           # Phase 2 monitor
  strategies/          # cross-chain arb, legs, balancer
  risk/                # caps, kill switch
  storage/             # SQLite models + repo
  live/                # paper + live runner
  backtest/            # replay detection DB
```

## Roadmap

Deferred phases: [roadmap.md](roadmap.md) (Azuro cross-protocol, in-play, parlays, V2 gated features).

## Cost floor (round-trip)

~4% Overtime fees (2% × 2 legs) + ~1.5% slippage + negligible L2 gas + ~0.04% bridge (measured). Threshold: **6% + safety buffer** in config.
