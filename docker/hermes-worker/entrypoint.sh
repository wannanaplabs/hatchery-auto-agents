#!/bin/bash
set -e

echo "[hermes-worker] WannaNapLabs Hermes Worker starting..."
echo "[hermes-worker] Model: MiniMax-M2.7 (orchestrator) + Claude Code CLI (coder)"
echo "[hermes-worker] Hatchery: ${HATCHERY_BASE_URL:-https://hatchery.run}"

# Git credentials
git config --global credential.helper store
if [ -n "$GITHUB_TOKEN" ]; then
    echo "https://${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    echo "[hermes-worker] GitHub token configured"
    # gh CLI reads GH_TOKEN/GITHUB_TOKEN from env; make sure it's exported for subprocess.
    export GH_TOKEN="$GITHUB_TOKEN"
fi

# Sanity-check MCP server is installed (non-fatal).
if [ -x /opt/hermes/venv/bin/hatchery-mcp ]; then
    echo "[hermes-worker] Hatchery MCP server available at /opt/hermes/venv/bin/hatchery-mcp"
else
    echo "[hermes-worker] WARN: hatchery-mcp binary not found — MCP tools disabled"
fi

# Create Hermes data dirs
mkdir -p /opt/data/{sessions,logs,memories,skills}

# Copy config if not present
if [ ! -f /opt/data/config.yaml ]; then
    cp /opt/hermes/docker/hermes-worker/config.yaml /opt/data/config.yaml 2>/dev/null || true
fi

# Create repos dir
mkdir -p /repos

# Run the worker (unbuffered so docker logs streams in real time)
export PYTHONUNBUFFERED=1
exec /opt/hermes/venv/bin/python3 -u /opt/hermes/wannanaplabs_worker.py
