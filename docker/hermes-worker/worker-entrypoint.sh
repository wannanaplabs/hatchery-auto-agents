#!/bin/bash
set -e

HERMES_HOME="/opt/data"
mkdir -p "$HERMES_HOME"/{sessions,logs,memories,skills}

# Copy config if not present
if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp /opt/data/config.yaml "$HERMES_HOME/config.yaml"
fi

# Set git config
git config --global user.name "Frank Nguyen"
git config --global user.email "frank.quy.nguyen@gmail.com"
git config --global credential.helper store
echo "https://${GITHUB_TOKEN}@github.com" > ~/.git-credentials

echo "[hermes-worker] Starting WannaNapLabs Hermes Worker"
echo "[hermes-worker] Model: MiniMax-M2.7 + Claude Code CLI"
echo "[hermes-worker] Hatchery: ${HATCHERY_BASE_URL:-https://hatchery-tau.vercel.app}"

# Run the worker loop
exec python3 /opt/hermes/wannanaplabs_worker.py
