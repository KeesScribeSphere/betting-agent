#!/usr/bin/env bash
# Weekly SQLite backup for Phase 2 detection (cron-friendly).
set -euo pipefail
ROOT="${1:-/opt/agent/betting-agent}"
DB="${ROOT}/data/agent.db"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${ROOT}/data/backups"
mkdir -p "$DEST"
sqlite3 "$DB" ".backup '${DEST}/agent-${STAMP}.db'"
find "$DEST" -name 'agent-*.db' -mtime +30 -delete
echo "backup: ${DEST}/agent-${STAMP}.db"
