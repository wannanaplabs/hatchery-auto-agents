#!/bin/bash
set -e

echo "[openhands-worker] WannaNapLabs OpenHands Worker starting..."
echo "[openhands-worker] Worker: ${WORKER_NAME:-openhands-worker}"
echo "[openhands-worker] LLM:    ${LLM_MODEL:-<unset>}"
echo "[openhands-worker] Base:   ${LLM_BASE_URL:-<default>}"
echo "[openhands-worker] Hatchery: ${HATCHERY_BASE_URL:-https://hatchery.run}"

# Probe OpenHands version (non-fatal)
if command -v openhands >/dev/null 2>&1; then
    ver=$(OPENHANDS_SUPPRESS_BANNER=1 openhands --version 2>&1 | head -1 || echo "unknown")
    echo "[openhands-worker] openhands CLI: $ver"
else
    echo "[openhands-worker] WARN: 'openhands' CLI not found on PATH"
fi

# Seed ~/.openhands/settings.json so the first-run wizard is skipped.
# --override-with-envs flag still trumps this at runtime, but having a file
# prevents any interactive prompt path from triggering in headless mode.
mkdir -p ~/.openhands
cat > ~/.openhands/settings.json <<JSON
{
  "llm": {
    "model": "${LLM_MODEL:-anthropic/claude-sonnet-4-5-20250929}",
    "api_key": "${LLM_API_KEY:-placeholder}",
    "base_url": "${LLM_BASE_URL:-}"
  },
  "security": {
    "confirmation_mode": false
  },
  "telemetry": {
    "disable": true
  }
}
JSON
echo "[openhands-worker] Seeded ~/.openhands/settings.json (model=${LLM_MODEL})"

# Git credentials (HTTPS only — credential helper needs plaintext URLs)
git config --global credential.helper store
if [ -n "$GITHUB_TOKEN" ]; then
    echo "https://${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    echo "[openhands-worker] GitHub token configured"
    export GH_TOKEN="$GITHUB_TOKEN"
fi

# Create repos dir
mkdir -p /repos /opt/data

# Run the worker (unbuffered)
export PYTHONUNBUFFERED=1
exec python3 -u /opt/oh/worker.py
