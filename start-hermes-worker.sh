#!/bin/bash
# Start the Hermes Worker Agent
# Uses MiniMax-M2.7 as orchestrator, Claude Code CLI as coder
#
# Usage:
#   ./start-hermes-worker.sh          # Run with Docker (preferred)
#   ./start-hermes-worker.sh --local  # Run without Docker (fallback)

set -e
cd "$(dirname "$0")"

# Load env
set -a
source .env.shared 2>/dev/null
set +a

if [ "$1" = "--local" ]; then
    echo "[hermes-worker] Running locally (no Docker)"
    echo "[hermes-worker] Model: MiniMax-M2.7 + Claude Code CLI"

    # Use Hermes venv
    HERMES_VENV=~/.hermes/hermes-agent/venv/bin/python3
    if [ ! -f "$HERMES_VENV" ]; then
        echo "ERROR: Hermes venv not found at $HERMES_VENV"
        echo "Install: cd ~/.hermes/hermes-agent && python3 -m venv venv && venv/bin/pip install -e '.[all]'"
        exit 1
    fi

    # Copy worker script to Hermes dir
    cp docker/hermes-worker/wannanaplabs_worker.py ~/.hermes/hermes-agent/wannanaplabs_worker.py

    exec $HERMES_VENV ~/.hermes/hermes-agent/wannanaplabs_worker.py
else
    echo "[hermes-worker] Running with Docker"

    # Check Docker
    if ! docker info >/dev/null 2>&1; then
        echo "ERROR: Docker not running. Use --local flag for non-Docker mode."
        exit 1
    fi

    # Build if needed
    if ! docker image inspect wannanaplabs/hermes-worker >/dev/null 2>&1; then
        echo "[hermes-worker] Building Docker image..."
        docker build -t wannanaplabs/hermes-worker -f docker/hermes-worker/Dockerfile docker/hermes-worker/
    fi

    # Run
    docker run -d --name hermes-worker \
        -e MINIMAX_API_KEY="$MINIMAX_API_KEY" \
        -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
        -e HATCHERY_API_KEY="$HATCHERY_API_KEY" \
        -e HATCHERY_BASE_URL="${HATCHERY_BASE_URL:-https://hatchery-tau.vercel.app}" \
        -e GITHUB_TOKEN="$GITHUB_TOKEN" \
        -v hermes-data:/opt/data \
        -v hermes-repos:/repos \
        wannanaplabs/hermes-worker

    echo "[hermes-worker] Container started. Logs: docker logs -f hermes-worker"
fi
