#!/bin/bash
# Start OpenHands-based Hatchery workers alongside the Hermes fleet.
# OpenHands competes on the same task queue — whoever claims first wins.
#
# Usage: ./scripts/start-openhands-perms.sh [claude|minimax|all]
#   (default: claude only, to minimize blast radius on first rollout)
set -e
cd "$(dirname "$0")/.."

MODE="${1:-claude}"

if [ ! -f .env.shared ]; then
  echo "Missing .env.shared"; exit 1
fi
set -a; . ./.env.shared; set +a

if ! docker image inspect wannanaplabs/openhands-worker >/dev/null 2>&1; then
  echo "Building openhands-worker image..."
  docker build -t wannanaplabs/openhands-worker \
    -f docker/openhands-worker/Dockerfile \
    docker/openhands-worker/
fi

# Perm definitions: name|LLM_MODEL|LLM_API_KEY_env|LLM_BASE_URL
# - claude:  Anthropic Claude Sonnet 4.5 — native Anthropic endpoint
# - minimax: MiniMax-M2.7 via OpenAI-compat shim. Note the `openai/` prefix so
#            litellm (OpenHands's backend) uses the OpenAI adapter with base_url.
PERMS_CLAUDE=(
  "openhands-claude|anthropic/claude-sonnet-4-5-20250929|ANTHROPIC_API_KEY|"
)
PERMS_MINIMAX=(
  # MiniMax via Anthropic-compat endpoint (same shim Hermes uses). The
  # `anthropic/` prefix makes litellm use its Anthropic adapter, which the
  # MiniMax /anthropic endpoint speaks natively.
  "openhands-minimax|anthropic/MiniMax-M2.7|MINIMAX_API_KEY|https://api.minimax.io/anthropic"
)

case "$MODE" in
  claude)   PERMS=("${PERMS_CLAUDE[@]}") ;;
  minimax)  PERMS=("${PERMS_MINIMAX[@]}") ;;
  all|both) PERMS=("${PERMS_CLAUDE[@]}" "${PERMS_MINIMAX[@]}") ;;
  *) echo "Unknown mode: $MODE. Use: claude | minimax | all"; exit 1 ;;
esac

for entry in "${PERMS[@]}"; do
  IFS='|' read -r name model key_var base_url <<< "$entry"
  # Resolve the API key variable indirectly
  api_key="${!key_var:-}"

  if [ -z "$api_key" ]; then
    echo "SKIP $name: $key_var is empty in .env.shared"
    continue
  fi

  # Per-agent Hatchery key (scoped /release, last_failed_by, cooldown)
  case "$name" in
    openhands-minimax) worker_htch_key=$(grep '^HATCHERY_API_KEY=' "$(dirname "$0")/../agents/qwen/config.env" 2>/dev/null | cut -d= -f2) ;;
    openhands-claude)  worker_htch_key=$(grep '^HATCHERY_API_KEY=' "$(dirname "$0")/../agents/gemma/config.env" 2>/dev/null | cut -d= -f2) ;;
    *)                 worker_htch_key="$HATCHERY_API_KEY" ;;
  esac
  [ -z "$worker_htch_key" ] && worker_htch_key="$HATCHERY_API_KEY"

  docker rm -f "$name" >/dev/null 2>&1 || true

  docker run -d --name "$name" --restart unless-stopped \
    -e WORKER_NAME="$name" \
    -e LLM_MODEL="$model" \
    -e LLM_API_KEY="$api_key" \
    -e LLM_BASE_URL="$base_url" \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    -e MINIMAX_API_KEY="${MINIMAX_API_KEY:-}" \
    -e HATCHERY_API_KEY="$worker_htch_key" \
    -e HATCHERY_BASE_URL="${HATCHERY_BASE_URL:-https://hatchery.run}" \
    -e GITHUB_TOKEN="$GITHUB_TOKEN" \
    -e GITHUB_ORG="${GITHUB_ORG:-wannanaplabs}" \
    -e POLL_INTERVAL="${POLL_INTERVAL:-30}" \
    -e OPENHANDS_TIMEOUT="${OPENHANDS_TIMEOUT:-600}" \
    -v openhands-repos:/repos \
    -v openhands-data:/opt/data \
    wannanaplabs/openhands-worker > /dev/null && \
    echo "started $name (model=$model key=${worker_htch_key:0:20}...)"
done

echo
echo "Running containers:"
docker ps --filter "name=openhands-" --format "  {{.Names}}\t{{.Status}}"
echo
echo "Tail logs: docker logs -f openhands-claude"
