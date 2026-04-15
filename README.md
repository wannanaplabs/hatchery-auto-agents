# Hatchery Auto-Agents

Autonomous AI coding agents that connect to Hatchery, receive jobs via webhook, and execute tasks end-to-end — cloning repos, writing code, deploying, and opening PRs.

## WannaNapLabs Fleet — 19 Projects

The fleet currently manages 18 OSINT visualization apps + 1 feedback system. Live state as of last update:

| # | Project | Status | Live URL | GitHub |
|---|---|---|---|---|
| 1 | **seismic-jukebox** — USGS earthquakes sonified | 🟢 LIVE | [seismic-jukebox-wannanaplabs.vercel.app](https://seismic-jukebox-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/seismic-jukebox) |
| 2 | **vanishing-green** — GLAD deforestation alerts | 🟢 LIVE | [vanishing-green-wannanaplabs.vercel.app](https://vanishing-green-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/vanishing-green) |
| 3 | **connected** — Multi-source correlation network | 🟢 LIVE | [connected-wannanaplabs.vercel.app](https://connected-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/connected) |
| 4 | **goop-ops** — Internal analytics dashboard | 🟢 LIVE | [goop-ops-wannanaplabs.vercel.app](https://goop-ops-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/goop-ops) |
| 5 | **burning-season** — NASA FIRMS wildfire timelapse | 🟢 LIVE | [burning-season-wannanaplabs.vercel.app](https://burning-season-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/burning-season) |
| 6 | **localized-threats** — ZIP-local safety score | 🟢 LIVE | [localized-threats-wannanaplabs.vercel.app](https://localized-threats-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/localized-threats) |
| 7 | **shell-game** — ICIJ Panama Papers force graph | 🟢 LIVE | [shell-game-wannanaplabs.vercel.app](https://shell-game-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/shell-game) |
| 8 | **newsquake** — GDELT news-as-seismograph | 🟢 LIVE | [newsquake-wannanaplabs.vercel.app](https://newsquake-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/newsquake) |
| 9 | **inside-track** — Politician trade detection | 🟢 LIVE | [inside-track-wannanaplabs.vercel.app](https://inside-track-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/inside-track) |
| 10 | **narrative-shift** — GDELT media sentiment | 🟢 LIVE | [narrative-shift-wannanaplabs.vercel.app](https://narrative-shift-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/narrative-shift) |
| 11 | **party-lines** — Dem vs Rep portfolios | 🟢 LIVE | [party-lines-wannanaplabs.vercel.app](https://party-lines-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/party-lines) |
| 12 | **orbital** — ISS tracker + SpaceX launches | 🟢 LIVE | [orbital-wannanaplabs.vercel.app](https://orbital-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/orbital) |
| 13 | **living-planet** — GBIF biodiversity observations | 🟢 LIVE | [living-planet-wannanaplabs.vercel.app](https://living-planet-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/living-planet) |
| 14 | **goop-feedback** — Fleet feedback widget + dashboard | 🟢 LIVE | [goop-feedback-wannanaplabs.vercel.app](https://goop-feedback-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/goop-feedback) |
| 15 | **pulse** — Earth-as-hospital EKG globe | 🔴 BROKEN | [pulse-wannanaplabs.vercel.app](https://pulse-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/pulse) |
| 16 | **dark-shipping** — AIS vessel gap detection | 🔴 BROKEN | [dark-shipping-wannanaplabs.vercel.app](https://dark-shipping-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/dark-shipping) |
| 17 | **anomaly-board** — Multi-source anomaly cards | 🔴 BROKEN | [anomaly-board-wannanaplabs.vercel.app](https://anomaly-board-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/anomaly-board) |
| 18 | **the-hill** — Capitol hemicycle + trade flashes | 🔴 BROKEN | [the-hill-wannanaplabs.vercel.app](https://the-hill-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/the-hill) |
| 19 | **toxic-clouds** — PurpleAir AQI map | 🔴 BROKEN | [toxic-clouds-wannanaplabs.vercel.app](https://toxic-clouds-wannanaplabs.vercel.app) | [repo](https://github.com/wannanaplabs/toxic-clouds) |

**Current tally: 14 LIVE · 5 BROKEN · 19 total.** Broken projects have `[FIX-DEPLOY]` tasks queued — fleet workers are iterating fixes.

### Related dashboards
- **Hatchery** (task queue + agent coordination) — [hatchery.run](https://hatchery.run)
- **goop-feedback dashboard** (user-reported bugs/suggestions triage) — [goop-feedback-wannanaplabs.vercel.app](https://goop-feedback-wannanaplabs.vercel.app)
- **GitHub org** — [github.com/wannanaplabs](https://github.com/wannanaplabs)

---


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
