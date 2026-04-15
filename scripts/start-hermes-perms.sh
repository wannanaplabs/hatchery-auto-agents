#!/bin/bash
# Start all 11 Hermes worker permutations.
# Each combo = brain (orchestrator) + coder (CODING_TOOL).
#
# Usage: ./scripts/start-hermes-perms.sh
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env.shared ]; then
  echo "Missing .env.shared"; exit 1
fi
set -a; . ./.env.shared; set +a

if ! docker image inspect wannanaplabs/hermes-worker >/dev/null 2>&1; then
  echo "Building hermes-worker image..."
  docker build -t wannanaplabs/hermes-worker -f docker/hermes-worker/Dockerfile docker/hermes-worker/
fi

# Brain options:
#   minimax  → MiniMax-M2.7 via api.minimax.io
#   qwen     → qwen2.5:7b via local Ollama
#   gemma    → gemma4:latest via local Ollama
#
# Coder options (CODING_TOOL):
#   claude-cli, ollama-qwen, ollama-gemma, ollama-deepseek, self
#
# Format: name|brain|coder
PERMS=(
  "hermes-claude|minimax|claude-cli"
  "hermes-self|minimax|self"
  "hermes-deepseek|minimax|ollama-deepseek"
)
# Note: qwen/gemma brain perms removed — qwen2.5:7b and gemma4 have 32K ctx,
# Hermes Agent requires 64K+. hermes-qwen/hermes-gemma (minimax brain + ollama coder)
# also removed for now to reduce MiniMax rate-limit pressure.

for entry in "${PERMS[@]}"; do
  IFS='|' read -r name brain coder <<< "$entry"

  case "$brain" in
    minimax)
      orch_model="MiniMax-M2.7"
      orch_url="https://api.minimax.io/anthropic"
      orch_key="$MINIMAX_API_KEY"
      ;;
    qwen)
      orch_model="qwen2.5:7b"
      orch_url="http://host.docker.internal:11434/v1"
      orch_key="ollama"
      ;;
    gemma)
      orch_model="gemma4:latest"
      orch_url="http://host.docker.internal:11434/v1"
      orch_key="ollama"
      ;;
  esac

  # Each worker gets its own per-agent Hatchery key — so /release, last_failed_by,
  # and claim cooldowns are scoped PER AGENT, not shared. This is the root fix
  # for the cross-fleet deadlock we hit when all workers used one Goop key.
  # Keys live in agents/<type>/config.env (gitignored, one-shot agent identities).
  case "$name" in
    hermes-claude)    worker_htch_key=$(grep '^HATCHERY_API_KEY=' "$(dirname "$0")/../agents/claude-code/config.env" 2>/dev/null | cut -d= -f2) ;;
    hermes-self)      worker_htch_key=$(grep '^HATCHERY_API_KEY=' "$(dirname "$0")/../agents/minimax/config.env" 2>/dev/null | cut -d= -f2) ;;
    hermes-deepseek)  worker_htch_key=$(grep '^HATCHERY_API_KEY=' "$(dirname "$0")/../agents/deepseek/config.env" 2>/dev/null | cut -d= -f2) ;;
    hermes-qwen)      worker_htch_key=$(grep '^HATCHERY_API_KEY=' "$(dirname "$0")/../agents/qwen/config.env" 2>/dev/null | cut -d= -f2) ;;
    hermes-gemma)     worker_htch_key=$(grep '^HATCHERY_API_KEY=' "$(dirname "$0")/../agents/gemma/config.env" 2>/dev/null | cut -d= -f2) ;;
    *)                worker_htch_key="$HATCHERY_API_KEY" ;;
  esac
  # Fallback to shared Goop key if per-agent key file missing
  [ -z "$worker_htch_key" ] && worker_htch_key="$HATCHERY_API_KEY"

  # Remove existing container if any
  docker rm -f "$name" >/dev/null 2>&1 || true

  docker run -d --name "$name" --restart unless-stopped \
    -e WORKER_NAME="$name" \
    -e CODING_TOOL="$coder" \
    -e ORCHESTRATOR_MODEL="$orch_model" \
    -e ORCHESTRATOR_URL="$orch_url" \
    -e ORCHESTRATOR_KEY="$orch_key" \
    -e MINIMAX_API_KEY="$MINIMAX_API_KEY" \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    -e HATCHERY_API_KEY="$worker_htch_key" \
    -e HATCHERY_BASE_URL="${HATCHERY_BASE_URL:-https://hatchery.run}" \
    -e GITHUB_TOKEN="$GITHUB_TOKEN" \
    -e OLLAMA_HOST="host.docker.internal:11434" \
    -v hermes-data:/opt/data \
    -v hermes-repos:/repos \
    wannanaplabs/hermes-worker > /dev/null && echo "started $name (brain=$brain coder=$coder key=${worker_htch_key:0:20}...)"
done

echo
echo "All started. Tail logs: docker logs -f hermes-claude"

# Start QA reviewer in background (single instance)
if ! pgrep -f "qa_reviewer.py" > /dev/null; then
  mkdir -p "$(dirname "$0")/../logs"
  nohup python3 "$(dirname "$0")/qa_reviewer.py" --loop 120 > "$(dirname "$0")/../logs/qa_reviewer.log" 2>&1 &
  echo "Started QA reviewer (pid=$!)"
fi
