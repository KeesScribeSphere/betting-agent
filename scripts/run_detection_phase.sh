#!/usr/bin/env bash
# Phase 2: run detection monitor for 14-21 days (operational — not automated in code)
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Starting detection monitor. Run 14-21 days, then: python scripts/analyze_detection.py"
exec python -m agent.cli detect
