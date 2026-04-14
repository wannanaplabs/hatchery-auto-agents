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
#     -e HATCHERY_BASE_URL="https://hatchery-tau.vercel.app" \
#     -e GITHUB_TOKEN="$GITHUB_TOKEN" \
#     -v hermes-data:/opt/data \
#     -v hermes-repos:/repos \
#     wannanaplabs/hermes-worker

FROM debian:bookworm-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    nodejs npm git curl tmux ripgrep build-essential libffi-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
