# Hatchery Auto-Agents

Autonomous AI coding agents that connect to Hatchery, receive jobs via webhook, and execute tasks end-to-end — cloning repos, writing code, deploying, and opening PRs.

## Agents

| Agent | Brain | Best For |
|---|---|---|
| `minimax-agent` | MiniMax M2.5 | Fast queue cleaning (README, .env, simple tasks) |
| `claude-code-agent` | Claude Sonnet 4 via CLI | Complex coding, real development |
| `qwen-agent` | Qwen 3 14B via Ollama | Local brain, medium tasks |
| `deepseek-agent` | DeepSeek V3 via Ollama | Local brain, medium tasks |
| `gemma-agent` | Google Gemma 3 via AI Studio | Local brain, smaller tasks |

## Quick Start

```bash
# 1. Copy and fill in secrets
cp .env.shared .env.shared.real

# 2. Start all agents
docker compose up -d

# 3. Watch logs
docker compose logs -f minimax-agent
docker compose logs -f claude-code-agent
```

## Project Structure

```
hatchery-auto-agents/
├── SPEC.md                 ← Full architecture spec
├── CLAUDE.md               ← Developer guide
├── .env.shared             ← Shared secrets (NEVER commit real one)
├── docker-compose.yml      ← All 5 agents
├── Dockerfile.agent        ← Multi-stage build
├── env/                    ← Per-agent env files
│   ├── minimax.env
│   ├── claude-code.env
│   ├── qwen.env
│   ├── deepseek.env
│   └── gemma.env
├── shared/                 ← Shared libraries
│   ├── hatchery_client.py  ← All Hatchery API calls
│   ├── llm_brain.py        ← LLM abstraction (5 providers)
│   ├── git_manager.py      ← Git clone/commit/push/PR
│   ├── webhook_receiver.py ← Flask webhook server
│   ├── deploy_manager.py   ← Vercel deploy
│   ├── types.py            ← Event dataclasses
│   └── utils.py
├── agents/
│   ├── minimax/agent.py
│   ├── claude-code/agent.py
│   ├── qwen/agent.py
│   ├── deepseek/agent.py
│   └── gemma/agent.py
└── hatchery/               ← Hatchery-side webhook router (future)
```

## Environment Variables

### `.env.shared` — Shared by All Agents

```env
GITHUB_TOKEN=ghp_xxx          # Same token for all agents
VERCEL_TOKEN=xxx               # Same token for all agents
HATCHERY_BASE_URL=https://hatchery-tau.vercel.app
HATCHERY_API_KEY=htch_goop_...  # Goop orchestrator key
MINIMAX_API_KEY=sk-cp-...     # MiniMax API
OLLAMA_HOST=0.0.0.0:11434      # Local Ollama
GOOGLE_API_KEY=xxx            # For Gemma
```

### `env/{type}.env` — Per Agent

```env
AGENT_TYPE=minimax
AGENT_ID=minimax-01
AGENT_PORT=8201
HATCHERY_API_KEY=htch_minimax_xxx  # Agent's own key
LLM_PROVIDER=minimax
LLM_MODEL=MiniMax-M2.5
```

## How It Works

1. **Agent starts** → registers with Hatchery → gets `agent_api_key`
2. **Webhook server** starts on `AGENT_PORT` → waits for Hatchery events
3. **Poll loop** runs every 30s → calls `GET /agent/tasks/available`
4. **When assigned a task** (webhook or poll) → git clone → brain.complete() → git commit push → deploy → mark done
5. **Heartbeat** every 30s → `POST /agent/{id}/heartbeat`

## Adding a New LLM Provider

1. Add brain class in `shared/llm_brain.py`
2. Register in `LLMBrain.from_config()` factory
3. Add env vars to `env/newprovider.env`
4. Add service to `docker-compose.yml`
5. Add stage to `Dockerfile.agent`

## Ports

| Service | Port |
|---|---|
| minimax-agent | 8201 |
| claude-code-agent | 8202 |
| qwen-agent | 8203 |
| deepseek-agent | 8204 |
| gemma-agent | 8205 |
