# VPS deployment runbook

Target host: Vultr Cloud Compute, Amsterdam, `ssh overtime-agent`

## First-time deploy

```bash
# On VPS as agent user
sudo mkdir -p /opt/agent /var/lib/agent /var/log/agent /etc/agent /var/backups/agent
sudo chown -R agent:agent /opt/agent /var/lib/agent /var/log/agent /var/backups/agent
sudo chmod 700 /etc/agent

cd /opt/agent
git clone <YOUR_REPO_URL> .
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
uv sync

cp config.example.yaml config.yaml
# Edit config.yaml RPC URLs if using Alchemy/Infura

sudo cp deploy/agent-detection.service /etc/systemd/system/
sudo cp deploy/logrotate-agent /etc/logrotate.d/agent
sudo systemctl daemon-reload
sudo systemctl enable agent-detection
```

## Secrets (`/etc/agent/env`)

```bash
sudo tee /etc/agent/env <<'EOF'
AGENT_PRIVATE_KEY=0x...
OVERTIME_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
EOF
sudo chmod 600 /etc/agent/env
sudo chown agent:agent /etc/agent/env
```

## Start detection (Phase 2)

```bash
sudo systemctl start agent-detection
sudo journalctl -u agent-detection -f
tail -F /var/log/agent/agent.jsonl | jq
```

Run **14–21 consecutive days** before analysis. Only one mode at a time.

## Updates

```bash
cd /opt/agent
git pull
uv sync
sudo systemctl restart agent-detection   # or agent-paper / agent-live
```

## Emergency stop

```bash
sudo systemctl stop agent-detection agent-paper agent-live
touch /var/lib/agent/kill-switch.flag
```

## Backup SQLite

```bash
sqlite3 /var/lib/agent/agent.db ".backup /var/backups/agent/agent-$(date +%F).db"
```

## Modes

| Service | Command | When |
|---------|---------|------|
| `agent-detection` | `detect` | Phase 2 — no capital |
| `agent-paper` | `paper` | Phase 4 — simulated trades |
| `agent-live` | `live` | Phase 5 — requires `AGENT_LIVE=1` |

## Smoke test after deploy

```bash
cd /opt/agent && .venv/bin/python -m agent.cli smoke --chain base
```
