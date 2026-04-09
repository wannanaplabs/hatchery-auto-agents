#!/bin/bash
# Start the Hatchery webhook router locally
set -e

cd "$(dirname "$0")/.."

export HATCHERY_DB_PATH="/tmp/hatchery-router.db"
export ROUTER_PORT=8090
# Optionally point to live Hatchery
# export HATCHERY_BASE_URL=https://hatchery-tau.vercel.app

pip install --quiet flask

exec python3 hatchery/server.py
