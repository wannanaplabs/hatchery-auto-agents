#!/bin/bash
#
# Start all Hatchery auto-agents in the background.
#
# Each agent is launched with its per-agent config, logs go to logs/<agent>.log,
# PIDs go to logs/<agent>.pid, and we preflight-check each agent's dependencies
# (API keys, Ollama, etc.) before launching. Agents that can't run are skipped
# with a clear reason.
#
# Usage:
#   ./start-all.sh            # Start all supported agents
#   ./start-all.sh minimax    # Start only the minimax agent
#   ./start-all.sh minimax qwen claude-code
#
# Stop everything:
#   ./stop-all.sh
#

set -e
cd "$(dirname "$0")"
ROOT="$PWD"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

# -----------------------------------------------------------
# Colors (if stdout is a tty)
# -----------------------------------------------------------
if [ -t 1 ]; then
    BLUE="\033[34m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
else
    BLUE=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi
say() { printf "${BLUE}[start-all]${RESET} %s\n" "$*"; }
ok()  { printf "  ${GREEN}OK${RESET}   %s\n" "$*"; }
skip(){ printf "  ${YELLOW}SKIP${RESET} %s\n" "$*"; }
warn(){ printf "  ${YELLOW}WARN${RESET} %s\n" "$*"; }
err() { printf "  ${RED}FAIL${RESET} %s\n" "$*"; }

# -----------------------------------------------------------
# Load shared env
# -----------------------------------------------------------
if [ ! -f ".env.shared" ]; then
    err "Missing .env.shared — cannot start any agent"
    exit 1
fi
# shellcheck disable=SC1091
set -a
# shellcheck disable=SC1091
. ./.env.shared
set +a

# -----------------------------------------------------------
# Preflight checks
# -----------------------------------------------------------
say "Preflight checks..."

# Python 3
if ! command -v python3 &>/dev/null; then
    err "python3 not found"
    exit 1
fi
ok "python3: $(python3 --version 2>&1)"

# Flask (needed by webhook_receiver and hatchery/server.py)
if ! python3 -c "import flask" 2>/dev/null; then
    warn "flask not installed (pip3 install flask) — agents will fail"
else
    ok "flask installed"
fi

# GitHub token
if [ -z "$GITHUB_TOKEN" ] || [[ "$GITHUB_TOKEN" == *REPLACE* ]]; then
    warn "GITHUB_TOKEN not set — git push/PR will fail (polling still works)"
else
    ok "GITHUB_TOKEN set"
fi

# Hatchery credentials
if [ -z "$HATCHERY_API_KEY" ] || [[ "$HATCHERY_API_KEY" == *REPLACE* ]]; then
    err "HATCHERY_API_KEY not set — cannot connect to Hatchery"
    exit 1
fi
ok "HATCHERY_API_KEY set"

# -----------------------------------------------------------
# Per-agent preflight — returns 0 if can run, 1 if should skip
# -----------------------------------------------------------
can_run_minimax() {
    if [ -z "$MINIMAX_API_KEY" ] || [[ "$MINIMAX_API_KEY" == *REPLACE* ]]; then
        echo "MINIMAX_API_KEY not set"
        return 1
    fi
    return 0
}

can_run_claude_code() {
    if ! command -v claude &>/dev/null; then
        echo "claude CLI not found (npm install -g @anthropic-ai/claude-code)"
        return 1
    fi
    return 0
}

can_run_ollama() {
    local model=$1
    if ! python3 -c "
import urllib.request, json, sys
try:
    with urllib.request.urlopen('http://${OLLAMA_HOST:-0.0.0.0:11434}/api/tags', timeout=3) as r:
        data = json.loads(r.read())
        models = [m['name'] for m in data.get('models', [])]
        if not any(m.startswith('${model}'.split(':')[0]) for m in models):
            sys.exit(2)
        sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        local code=$?
        if [ "$code" = "1" ]; then
            echo "Ollama not running at ${OLLAMA_HOST:-0.0.0.0:11434}"
        else
            echo "Model '$model' not pulled (ollama pull $model)"
        fi
        return 1
    fi
    return 0
}

can_run_gemma() {
    # Read provider from agent config — defaults to ollama
    local provider
    provider=$(grep -E '^LLM_PROVIDER=' "agents/gemma/config.env" 2>/dev/null | cut -d= -f2 | tr -d '"')
    provider="${provider:-ollama}"
    if [ "$provider" = "ollama" ]; then
        local model
        model=$(grep -E '^LLM_MODEL=' "agents/gemma/config.env" 2>/dev/null | cut -d= -f2 | tr -d '"')
        can_run_ollama "${model:-gemma3:4b}"
        return $?
    fi
    # Fallback: google provider
    if [ -z "$GOOGLE_API_KEY" ] || [[ "$GOOGLE_API_KEY" == *REPLACE* ]]; then
        echo "GOOGLE_API_KEY not set in .env.shared (or switch LLM_PROVIDER=ollama)"
        return 1
    fi
    return 0
}

# -----------------------------------------------------------
# Launch an agent
# -----------------------------------------------------------
launch_agent() {
    local agent=$1
    local config_file="agents/$agent/config.env"
    local log_file="$LOG_DIR/$agent.log"
    local pid_file="$LOG_DIR/$agent.pid"

    if [ ! -f "$config_file" ]; then
        err "$agent — missing $config_file"
        return 1
    fi

    # If already running, skip
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        skip "$agent — already running (pid=$(cat "$pid_file"))"
        return 0
    fi

    # Use Python -u for unbuffered output so `tail -f` works immediately.
    # Use nohup so the agent survives the terminal closing.
    AGENT_ENV_FILE="$config_file" nohup \
        python3 -u -m "agents.${agent}.agent" \
        >"$log_file" 2>&1 &
    local pid=$!
    echo $pid > "$pid_file"

    # Give it 2 seconds to crash on startup
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        ok "$agent — started (pid=$pid, log=$log_file)"
        return 0
    else
        err "$agent — crashed on startup. Last 10 lines:"
        tail -10 "$log_file" | sed 's/^/       /'
        rm -f "$pid_file"
        return 1
    fi
}

# -----------------------------------------------------------
# Determine which agents to start
# -----------------------------------------------------------
if [ $# -gt 0 ]; then
    AGENTS=("$@")
else
    AGENTS=("minimax" "claude-code" "qwen" "deepseek" "gemma")
fi

say "Launching agents: ${AGENTS[*]}"
echo

started=()
skipped=()
failed=()

for agent in "${AGENTS[@]}"; do
    case "$agent" in
        minimax)
            if reason=$(can_run_minimax); then
                launch_agent "$agent" && started+=("$agent") || failed+=("$agent")
            else
                skip "$agent — $reason"
                skipped+=("$agent")
            fi
            ;;
        claude-code)
            if reason=$(can_run_claude_code); then
                launch_agent "$agent" && started+=("$agent") || failed+=("$agent")
            else
                skip "$agent — $reason"
                skipped+=("$agent")
            fi
            ;;
        qwen)
            # Source agent config to get LLM_MODEL
            model=$(grep -E '^LLM_MODEL=' "agents/qwen/config.env" 2>/dev/null | cut -d= -f2 | tr -d '"')
            if reason=$(can_run_ollama "${model:-qwen2.5:7b}"); then
                launch_agent "$agent" && started+=("$agent") || failed+=("$agent")
            else
                skip "$agent — $reason"
                skipped+=("$agent")
            fi
            ;;
        deepseek)
            model=$(grep -E '^LLM_MODEL=' "agents/deepseek/config.env" 2>/dev/null | cut -d= -f2 | tr -d '"')
            if reason=$(can_run_ollama "${model:-deepseek-r1:8b}"); then
                launch_agent "$agent" && started+=("$agent") || failed+=("$agent")
            else
                skip "$agent — $reason"
                skipped+=("$agent")
            fi
            ;;
        gemma)
            if reason=$(can_run_gemma); then
                launch_agent "$agent" && started+=("$agent") || failed+=("$agent")
            else
                skip "$agent — $reason"
                skipped+=("$agent")
            fi
            ;;
        *)
            err "$agent — unknown agent type"
            failed+=("$agent")
            ;;
    esac
done

echo
say "Summary"
printf "  ${GREEN}started:${RESET}  %s\n" "${started[*]:-none}"
printf "  ${YELLOW}skipped:${RESET}  %s\n" "${skipped[*]:-none}"
printf "  ${RED}failed:${RESET}   %s\n" "${failed[*]:-none}"

if [ ${#started[@]} -gt 0 ]; then
    echo
    say "Logs: tail -f logs/{${started[*]// /,}}.log"
    say "Stop: ./stop-all.sh"
fi

# Exit 0 if anything started, 1 otherwise
[ ${#started[@]} -gt 0 ] && exit 0 || exit 1

# Hermes worker is available as: hermes_worker.py
# Run separately: ~/.hermes/hermes-agent/venv/bin/python3 hermes_worker.py
