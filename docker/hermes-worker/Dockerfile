# WannaNapLabs Hermes Worker
# NousResearch/hermes-agent + Claude Code CLI
#
# Build:
#   cd ~/hatchery-auto-agents
#   docker build -t wannanaplabs/hermes-worker -f docker/hermes-worker/Dockerfile docker/hermes-worker/
#
# Run:
#   docker run -d --name hermes-worker \
#     -e MINIMAX_API_KEY="$MINIMAX_API_KEY" \
#     -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
#     -e HATCHERY_API_KEY="$HATCHERY_API_KEY" \
#     -e HATCHERY_BASE_URL="https://hatchery.run" \
#     -e GITHUB_TOKEN="$GITHUB_TOKEN" \
#     -v hermes-data:/opt/data \
#     -v hermes-repos:/repos \
#     wannanaplabs/hermes-worker

FROM debian:bookworm-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    nodejs npm git curl tmux ripgrep build-essential libffi-dev ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI (needed for PR-based task flow)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null && \
    chmod a+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code 2>/dev/null || echo "Claude Code install failed — will retry"

# Clone hermes-agent from NousResearch
RUN git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /opt/hermes

WORKDIR /opt/hermes

# Create venv and install Hermes deps
RUN python3 -m venv /opt/hermes/venv && \
    /opt/hermes/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /opt/hermes/venv/bin/pip install --no-cache-dir -e ".[all]" 2>/dev/null || \
    /opt/hermes/venv/bin/pip install --no-cache-dir \
      fire openai httpx pyyaml rich textual prompt_toolkit \
      aiohttp websockets pillow requests beautifulsoup4

# Install Hatchery MCP server (not yet on PyPI — install from git).
# Exposes get_context, claim_task, update_task_status, checkin, messages, projects, etc.
RUN /opt/hermes/venv/bin/pip install --no-cache-dir \
      git+https://github.com/wannanaplabs/hatchery-mcp.git \
    || echo "hatchery-mcp install failed — worker will still run without MCP tools"

# Register hatchery-mcp with the Claude Code CLI (per-user config at /root/.claude.json).
# Env vars are resolved by Claude CLI at runtime from the container environment.
RUN mkdir -p /root && printf '%s' '{"mcpServers":{"hatchery":{"command":"/opt/hermes/venv/bin/hatchery-mcp","env":{"HATCHERY_API_KEY":"${HATCHERY_API_KEY}","HATCHERY_BASE_URL":"https://hatchery.run"}}}}' > /root/.claude.json

# Volumes
ENV HERMES_HOME=/opt/data
ENV PYTHONPATH=/opt/hermes
VOLUME ["/opt/data", "/repos"]

# Copy our worker files
COPY config.yaml /opt/default-config.yaml
COPY wannanaplabs_worker.py /opt/hermes/wannanaplabs_worker.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Git defaults
RUN git config --global user.name "Frank Nguyen" && \
    git config --global user.email "frank.quy.nguyen@gmail.com" && \
    git config --global credential.helper store

ENTRYPOINT ["/entrypoint.sh"]
