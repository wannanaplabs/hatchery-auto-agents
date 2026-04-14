#!/bin/bash
#
# Stop all Hatchery auto-agents started by start-all.sh.
#
# Usage:
#   ./stop-all.sh            # Stop every agent with a PID file in logs/
#   ./stop-all.sh minimax    # Stop only the minimax agent
#

set -e
cd "$(dirname "$0")"
LOG_DIR="./logs"

if [ -t 1 ]; then
    BLUE="\033[34m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
else
    BLUE=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi
say() { printf "${BLUE}[stop-all]${RESET} %s\n" "$*"; }
ok()  { printf "  ${GREEN}OK${RESET}   %s\n" "$*"; }
warn(){ printf "  ${YELLOW}WARN${RESET} %s\n" "$*"; }

if [ ! -d "$LOG_DIR" ]; then
    say "No logs/ dir — nothing to stop"
    exit 0
fi

if [ $# -gt 0 ]; then
    AGENTS=("$@")
else
    AGENTS=()
    for pid_file in "$LOG_DIR"/*.pid; do
        [ -f "$pid_file" ] || continue
        agent=$(basename "$pid_file" .pid)
        AGENTS+=("$agent")
    done
fi

if [ ${#AGENTS[@]} -eq 0 ]; then
    say "No running agents found"
    exit 0
fi

say "Stopping: ${AGENTS[*]}"

for agent in "${AGENTS[@]}"; do
    pid_file="$LOG_DIR/$agent.pid"
    if [ ! -f "$pid_file" ]; then
        warn "$agent — no pid file"
        continue
    fi
    pid=$(cat "$pid_file")
    if ! kill -0 "$pid" 2>/dev/null; then
        warn "$agent — pid $pid not running"
        rm -f "$pid_file"
        continue
    fi
    kill -TERM "$pid" 2>/dev/null || true

    # Wait up to 5 seconds for clean shutdown
    for i in 1 2 3 4 5; do
        if ! kill -0 "$pid" 2>/dev/null; then break; fi
        sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
        warn "$agent — did not exit, sending SIGKILL"
        kill -9 "$pid" 2>/dev/null || true
        sleep 0.5
    fi

    ok "$agent — stopped (pid $pid)"
    rm -f "$pid_file"
done
