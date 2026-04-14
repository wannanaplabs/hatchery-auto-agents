#!/bin/bash
# Start a Hatchery agent with real credentials from gh CLI + environment
set -e

AGENT_TYPE="${AGENT_TYPE:-minimax}"
AGENT_ID="${AGENT_ID:-agent-01}"
AGENT_NAME="${AGENT_NAME:-Agent 01}"
AGENT_PORT="${AGENT_PORT:-8201}"
AGENT_WEBHOOK_URL="${AGENT_WEBHOOK_URL:-http://localhost:${AGENT_PORT}/webhook}"

# Get GitHub token from gh CLI (fails if not authenticated)
if command -v gh &>/dev/null; then
    export GITHUB_TOKEN=$(gh auth token)
    echo "[start-agent] GitHub token: $(echo $GITHUB_TOKEN | cut -c1-8)..."
fi

# SSL cert fix for macOS Python
if command -v python3 &>/dev/null; then
    export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())" 2>/dev/null || echo "")
    export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
fi

# Don't cache .pyc files (prevents stale code issues)
export PYTHONDONTWRITEBYTECODE=1

echo "[start-agent] Starting ${AGENT_TYPE} as ${AGENT_ID} on port ${AGENT_PORT}"
echo "[start-agent] HATCHERY_BASE_URL=${HATCHERY_BASE_URL:-https://hatchery-tau.vercel.app}"

cd ~/hatchery-auto-agents

exec python3 -m agents.${AGENT_TYPE}.agent
