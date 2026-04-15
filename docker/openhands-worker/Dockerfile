# WannaNapLabs OpenHands Worker
# OpenHands (All-Hands-AI) as the coding loop — competes on the same Hatchery queue
# as the Hermes workers. OpenHands's edit->build->test->retry loop scored ~53% on
# SWE-bench Verified as of early 2026, vs Hermes's ~10-20%.
#
# Build:
#   cd ~/hatchery-auto-agents
#   docker build -t wannanaplabs/openhands-worker -f docker/openhands-worker/Dockerfile docker/openhands-worker/
#
# Run (via scripts/start-openhands-perms.sh, or manually):
#   docker run -d --name openhands-claude \
#     -e WORKER_NAME=openhands-claude \
#     -e LLM_MODEL="anthropic/claude-sonnet-4-5-20250929" \
#     -e LLM_API_KEY="$ANTHROPIC_API_KEY" \
#     -e HATCHERY_API_KEY="$HATCHERY_API_KEY" \
#     -e GITHUB_TOKEN="$GITHUB_TOKEN" \
#     -v openhands-repos:/repos \
#     wannanaplabs/openhands-worker

# Use python:3.12 as base — OpenHands (current) requires Python 3.12+.
# The `uv tool install openhands` path is the vendor-blessed install method.
FROM python:3.12-slim-bookworm

# System deps — match Hermes worker so we can build/test Next.js projects.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg git tmux ripgrep build-essential libffi-dev \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (needed for PR creation via gh)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null && \
    chmod a+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*

# Install `uv` (vendor-recommended installer for the OpenHands CLI).
# https://docs.openhands.dev/openhands/usage/cli/installation
RUN pip install --no-cache-dir uv

# Install the OpenHands CLI as a uv tool. Binaries land in /root/.local/bin.
# The CLI wires up litellm internally, so LLM_MODEL / LLM_API_KEY / LLM_BASE_URL
# env vars route to Anthropic, OpenAI-compat endpoints (MiniMax), etc.
RUN uv tool install openhands --python 3.12
ENV PATH="/root/.local/bin:${PATH}"

# Hatchery MCP (optional — OpenHands supports MCP servers via ~/.openhands/settings.json)
RUN pip install --no-cache-dir \
      git+https://github.com/wannanaplabs/hatchery-mcp.git \
    || echo "hatchery-mcp install failed — worker runs without MCP"

# Volumes for persisted repos + OpenHands session state
VOLUME ["/repos", "/opt/data"]

WORKDIR /opt/oh

COPY worker.py /opt/oh/worker.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Git defaults (shared credential helper with Hermes — matches Frank's identity)
RUN git config --global user.name "Frank Nguyen" && \
    git config --global user.email "frank.quy.nguyen@gmail.com" && \
    git config --global credential.helper store

ENTRYPOINT ["/entrypoint.sh"]
