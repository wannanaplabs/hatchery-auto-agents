#!/bin/bash
# Start the minimax agent
set -e
cd "$(dirname "$0")"

# Load shared env first, then agent-specific config
export $(grep -v '^#' ../../.env.shared | xargs)
export $(grep -v '^#' config.env | xargs)

exec python3 -m agents.minimax.agent
