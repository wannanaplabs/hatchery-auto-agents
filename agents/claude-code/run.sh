#!/bin/bash
# Start the Claude Code agent
set -e
cd "$(dirname "$0")"

# Load shared env first, then agent-specific config
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export $(grep -v '^#' "$SCRIPT_DIR/../../.env.shared" 2>/dev/null | xargs 2>/dev/null || true)
export $(grep -v '^#' config.env | xargs)

exec python3 -m agents.claude-code.agent
