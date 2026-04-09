# Hatchery Autonomous Agents — Technical Specification

**Location:** `~/hatchery-auto-agents/`
**Last updated:** 2026-04-09

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Agents](#3-agents)
4. [Shared Libraries](#4-shared-libraries)
5. [Environment Configuration](#5-environment-configuration)
6. [Types Reference](#6-types-reference)
7. [Webhook System](#7-webhook-system)
8. [Agent Registration & Lifecycle](#8-agent-registration--lifecycle)
9. [Coding Pipeline](#9-coding-pipeline)
10. [Docker](#10-docker)
11. [Adding New Agents](#11-adding-new-agents)
12. [Adding New LLM Providers](#12-adding-new-llm-providers)
13. [Agent-to-Agent Messaging Protocol](#13-agent-to-agent-messaging-protocol)
14. [Hatchery-Side Changes Needed](#14-hatchery-side-changes-needed)
15. [Current Status](#15-current-status)

---

## 1. Overview

Five autonomous coding agents connect to Hatchery, receive jobs via webhook or polling, and execute tasks end-to-end: clone repo → generate code → write files → commit → push → deploy → open PR.

Each agent is identical in structure, differing only in which LLM brain powers it.

| Agent | Brain | Model | Best For |
|---|---|---|---|
| `minimax-agent` | MiniMax API | M2.5 / M2.7 | Fast queue cleaning (docs, links, simple tasks) |
| `claude-code-agent` | Claude Code CLI | Sonnet 4 / Opus 4 | Complex coding, real development |
| `qwen-agent` | Ollama (local) | Qwen 3 14B | Medium tasks, no API cost |
| `deepseek-agent` | Ollama (local) | DeepSeek V3 | Medium tasks, no API cost |
| `gemma-agent` | Google AI Studio | Gemma 3 27B | Smaller tasks via Gemini API |

---

## 2. Architecture

```
                          ┌─────────────────────────────────────────────┐
                          │              HATCHERY PLATFORM              │
                          │                                              │
                          │  Task Queue (90 tasks across 15 projects)   │
                          │  Agent Registry (online/offline/busy)        │
                          │  Message Bus (agent↔agent)                   │
                          │  Project Spec (github_repo, stack, etc.)     │
                          └──────────────────────┬──────────────────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    │  Hatchery Webhook Router   │  (hatchery/server.py)      │
                    │  POST /register            │  POST /dispatch            │
                    │  POST /broadcast           │  POST /messages            │
                    └────────────────────────────┬────────────────────────────┘
                                                 │
                    ┌────────────────────────────┴────────────────────────────┐
                    │              INTERNET / Tailscale                       │
                    │  webhooks POSTed to agent:PORT/webhook                 │
                    └────────────────────────────┬────────────────────────────┘
                    ┌────────────────────────────┼────────────────────────────┐
                    │  Per-agent Flask webhook    │  Ports 8201–8205          │
                    │  server (shared/            │                            │
                    │  webhook_receiver.py)       │                            │
                    └────────────────────────────┬────────────────────────────┘
                                                 │
  ┌─────────────────────────────────────────────┼──────────────────────────┐
  │  BASE AGENT (shared/base_agent.py)          │                          │
  │  ┌─────────────┐ ┌─────────────┐ ┌─────────┴───────┐ ┌────────────────┐  │
  │  │ hatchery_   │ │ webhook_    │ │ task_executor   │ │ CodeParser    │  │
  │  │ client      │ │ receiver    │ │ (git→brain→     │ │ (LLM→files)   │  │
  │  │             │ │             │ │  write→push)   │ │                │  │
  │  └─────────────┘ └─────────────┘ └─────────────────┘ └────────────────┘  │
  │  ┌─────────────┐ ┌─────────────┐ ┌─────────┴───────┐ ┌────────────────┐  │
  │  │ git_manager │ │ deploy_     │ │ heartbeat_loop │ │ poll_loop     │  │
  │  │             │ │ manager     │ │                │ │                │  │
  │  └─────────────┘ └─────────────┘ └─────────────────┘ └────────────────┘  │
  └─────────────────────────────────────────────┼──────────────────────────┘
                    │                            │
  ┌─────────────────┼────────────────────────────┴────────────────────────┐
  │  LLM Brains     │  (shared/llm_brain.py)                             │
  │  ┌───────────┐  │  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
  │  │ MiniMax   │  │  │ OllamaBrain│  │ GeminiBrain│  │ ClaudeCodeBrain│  │
  │  │Brain      │  │  │(Qwen+DS)  │  │(Gemma)     │  │(Sonnet CLI)    │  │
  │  └───────────┘  │  └───────────┘  └───────────┘  └────────────────┘  │
  └─────────────────┼─────────────────────────────────────────────────────┘
                   │
  ┌────────────────┴─────────────────────────────────────────────────────┐
  │  GITHUB / VERCELa                                                    │
  │  github.com/wannanaplabs/{slug}  →  clone / push / PR               │
  │  Vercel deploy + smoke test                                          │
  └──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Agents

Each agent lives in `agents/{type}/`:

```
agents/{type}/
├── agent.py      # Agent implementation (subclass of BaseAgent)
├── config.env    # Per-agent env vars (AGENT_ID, AGENT_PORT, etc.)
└── run.sh        # Startup script
```

### 3.1 Agent Entry Point

All agents use the same `BaseAgent` from `shared/base_agent.py`. Each agent's `agent.py` only overrides:

```python
class MinimaxAgent(BaseAgent):
    agent_type = "minimax"

    def create_brain(self):
        return LLMBrain.from_config(
            provider="minimax",
            api_key=self.cfg.minimax_api_key,
            model=self.cfg.llm_model,
            base_url=self.cfg.minimax_base_url,
        )
```

### 3.2 Agent Lifecycle

```
1. Load .env.shared + agents/{type}/config.env
2. Build AgentConfig from environment
3. HatcheryClient.register() → get agent_api_key
4. WebhookReceiver.start() on AGENT_PORT
5. Heartbeat thread starts (POST /agent/{id}/heartbeat every 30s)
6. Main poll loop starts (GET /agent/tasks/available every 30s)
7. On task.assigned webhook: acknowledge immediately, execute async
8. On SIGINT/SIGTERM: mark task blocked, exit gracefully
```

### 3.3 Task Execution Flow

```
claim_task()
  ↓
git clone_or_pull(github_repo)
  ↓
git new_branch("feat/hatchery-{title-sanspecial}-{task_id[:8]}")
  ↓
brain.complete(prompt, system_prompt)   ← LLM generates code
  ↓
CodeParser.parse(response, repo_dir)    ← Extract file writes
  ↓
CodeParser.apply_writes()               ← Write files to disk
  ↓
git add_commit("feat({task_id[:8]}): {title} [Hatchery task]")
  ↓
git push
  ↓
deploy_manager.deploy()                ← Vercel API (optional)
  ↓
git_manager.open_pr()                  ← gh CLI (optional)
  ↓
hatchery.update_task_status(task_id, "done", comment="...")
  ↓
clear_task_context()                   ← Remove checkpoint file
```

---

## 4. Shared Libraries

All located in `shared/`. Every agent imports from here — no code duplication.

### 4.1 `shared/base_agent.py` — `BaseAgent`

**Main class:** `BaseAgent`

| Method | Description |
|---|---|
| `register()` | POST to Hatchery `/agent/register`, store `agent_api_key` |
| `run()` | Full startup: register → webhook → heartbeat → poll loop |
| `create_brain()` | Override in subclass — return an `LLMBrain` instance |
| `_execute_task(task)` | Full pipeline: claim → git → brain → parse → commit → deploy → done |
| `_on_task_assigned(event)` | Webhook handler for `task.assigned` |
| `_on_message_received(event)` | Webhook handler for `message.received` |
| `_on_broadcast(event)` | Webhook handler for `broadcast` |
| `_poll_loop()` | Main loop: poll available tasks every 30s |
| `_heartbeat_loop()` | Thread: POST heartbeat every 30s |

**Subclass hooks:**

```python
class MyAgent(BaseAgent):
    agent_type = "my-agent"          # Required: string identifier
    system_prompt = "..."            # Optional: override system prompt

    def create_brain(self):
        return LLMBrain.from_config(
            provider="my-provider",
            api_key=self.cfg.my_api_key,
            model=self.cfg.llm_model,
        )
```

### 4.2 `shared/hatchery_client.py` — `HatcheryClient`

Wrapper around Hatchery REST API.

```python
client = HatcheryClient(api_key="htch_...", base_url="https://hatchery-tau.vercel.app")

# Registry
client.register(agent_config)              # → {"agent_api_key": "...", ...}
client.heartbeat(agent_id, status="alive", current_task_id="...", progress_pct=50)

# Tasks
client.get_available_tasks()               # → [task, ...]
client.claim_task(task_id)                 # → {}
client.update_task_status(task_id, "in_progress", progress_pct=25)
client.update_task_status(task_id, "done", comment="Completed by agent")
client.get_context()                       # → {current_task, workspace, ...}

# Messaging
client.send_message(to_agent_id, content, channel="direct")
client.reply_to_message(message_id, content)
client.broadcast(content)
```

### 4.3 `shared/llm_brain.py` — `LLMBrain`

Pluggable LLM brain. Factory: `LLMBrain.from_config(provider, api_key, model, **kwargs)`.

| Class | Provider | Model Example | Notes |
|---|---|---|---|
| `MiniMaxBrain` | `minimax` | `MiniMax-M2.5` | Fast, cheap API |
| `OllamaBrain` | `ollama` | `qwen3:14b`, `deepseek-v3` | Local, no API cost |
| `GeminiBrain` | `google` | `gemma-3-27b` | Via AI Studio API |
| `ClaudeCodeBrain` | `anthropic` | `claude-sonnet-4-5` | Via `claude --print` CLI |
| `OpenAIBrain` | `openai` | `gpt-4o` | Backup |

**Interface:**
```python
brain = LLMBrain.from_config(provider="minimax", api_key="...", model="M2.5")
response = brain.complete(
    prompt="Write a hello world function",
    system="You are a coding agent.",
    max_tokens=4096,
)  # → str (the LLM's text response)
```

### 4.4 `shared/git_manager.py` — `GitManager`

Handles all git operations.

```python
git = GitManager(github_token="ghp_...")

repo_dir = git.clone_or_pull("https://github.com/wannanaplabs/toxic-clouds")
# → Path("/Users/.../hatchery-repos/toxic-clouds")

git.new_branch("feat/hatchery-my-task-abc12345")
git.add_commit("feat: my task [Hatchery task]")
git.push()

pr = git.open_pr(
    title="[Hatchery] My Task",
    body="Completes Hatchery task abc12345",
)
# → {"url": "https://github.com/..."} or {"error": "..."}
```

**How auth works:** Token is stored in `~/.git-credentials` so all git operations (clone, push) authenticate automatically via the credential helper.

### 4.5 `shared/webhook_receiver.py` — `WebhookReceiver`

Flask-based HTTP server that receives webhooks from Hatchery.

```python
receiver = WebhookReceiver(
    port=8201,
    agent_api_key="agnt_xxx",
    event_handlers={
        "task.assigned": my_agent._on_task_assigned,
        "message.received": my_agent._on_message_received,
        "broadcast": my_agent._on_broadcast,
    },
)
receiver.start()  # Starts in background thread

# POST /webhook → validates Bearer token → calls appropriate handler
# POST /health  → {"status": "ok", "agent": "minimax-01"}
```

**Authentication:** Every POST to `/webhook` must include `Authorization: Bearer {agent_api_key}`. Requests with wrong/missing tokens get `401`/`403`.

### 4.6 `shared/deploy_manager.py` — `DeployManager`

```python
deploy = DeployManager(vercel_token="...", github_token="...")

result = deploy.deploy(repo_dir, vercel_project_id="prj_xxx")
# → {"url": "https://toxic-clouds.vercel.app", "id": "dpl_xxx", "status": "READY"}

ok = deploy.smoke_test("https://toxic-clouds.vercel.app")
# → True / False
```

### 4.7 `shared/types.py` — Dataclasses

```python
# Webhook event types (all dataclasses)
TaskAssignedEvent       # event="task.assigned"
MessageReceivedEvent    # event="message.received"
BroadcastEvent          # event="broadcast"
TaskUpdatedEvent        # event="task.updated"
TaskTransferredEvent    # event="task.transferred"

AgentConfig             # All config fields loaded from env
AgentRegistration      # Data sent during registration
HatcheryTask            # Task object from API
```

### 4.8 `shared/utils.py` — Utilities

```python
setup_logging(name="my-agent")       # Configure logging
load_env_file("path/to/.env")        # Parse and set env vars
load_shared_env(base_dir)            # Load .env.shared
save_task_context(agent_id, ...)      # Write task checkpoint
load_task_context(agent_id)           # Read checkpoint (for resume)
clear_task_context(agent_id)          # Remove checkpoint
ensure_dir(path)                      # mkdir -p
read_json(path) / write_json(path, data)  # JSON helpers
```

### 4.9 `shared/base_agent.py` — `CodeParser`

Parses LLM output into file writes.

```python
CodeParser.parse(text, repo_dir)  # → {Path("/abs/path"): "file content\n"}
CodeParser.apply_writes(writes)   # Writes all files, returns [str(path), ...]
```

**Three formats recognized:**

1. **JSON manifest (preferred):**
   ```json
   {
     "files": [
       {"path": "src/app.ts", "content": "export default ...\n"}
     ]
   }
   ```

2. **Fenced code blocks with path in language tag:**
   ````markdown
   ```src/app.ts
   export default function App() { ... }
   ```
   ````

3. **CREATE: directive:**
   ```markdown
   CREATE: src/app.ts
   ---
   export default function App() { ... }
   ```

---

## 5. Environment Configuration

### 5.1 `.env.shared` — Shared by All Agents

| Variable | Description | Example |
|---|---|---|
| `GITHUB_TOKEN` | GitHub personal access token for clone/push/PR | `ghp_xxx` |
| `VERCEL_TOKEN` | Vercel API token for deployments | `xxx` |
| `GIT_AUTHOR_NAME` | Git author name for commits | `Hatchery Agent` |
| `GIT_AUTHOR_EMAIL` | Git author email | `agent@hatchery.local` |
| `HATCHERY_BASE_URL` | Hatchery API base URL | `https://hatchery-tau.vercel.app` |
| `HATCHERY_API_KEY` | Goop's orchestrator key (admin access) | `htch_goop_...` |
| `MINIMAX_API_KEY` | MiniMax API key | `sk-cp-...` |
| `MINIMAX_BASE_URL` | MiniMax endpoint | `https://api.minimaxi.chat/v1` |
| `OLLAMA_HOST` | Local Ollama host | `0.0.0.0:11434` |
| `GOOGLE_API_KEY` | Google AI Studio key (for Gemma) | `AIzaSy...` |

### 5.2 `env/{type}.env` — Per Agent

| Variable | Description | Example |
|---|---|---|
| `AGENT_TYPE` | Agent type identifier | `minimax` |
| `AGENT_ID` | Unique agent ID | `minimax-01` |
| `AGENT_NAME` | Human-readable name | `MiniMax Worker 1` |
| `AGENT_PORT` | Webhook receiver port | `8201` |
| `AGENT_WEBHOOK_URL` | Public URL Hatchery POSTs to | `http://host:8201/webhook` |
| `HATCHERY_API_KEY` | Agent's own Hatchery key (not Goop's) | `htch_minimax_...` |
| `LLM_PROVIDER` | Which LLM brain to use | `minimax` |
| `LLM_MODEL` | Exact model name | `MiniMax-M2.5` |
| `WANNAFUN_WS` | Preferred workspace ID | `60d513d2-...` |

### 5.3 `agents/{type}/config.env` — Agent Startup Config

Same as `env/{type}.env` but loaded at runtime by the agent's `run.sh`.

### 5.4 Hatchery Router env (`hatchery/`)

| Variable | Description | Default |
|---|---|---|
| `HATCHERY_DB_PATH` | SQLite DB path for agent registry | `/tmp/hatchery-router.db` |
| `ROUTER_PORT` | Port for router Flask server | `8090` |
| `HATCHERY_WS` | Default workspace ID | `60d513d2-...` |

---

## 6. Types Reference

### `AgentConfig`

Full agent configuration loaded from environment variables.

```python
@dataclass
class AgentConfig:
    agent_type: str          # "minimax", "claude-code", etc.
    agent_id: str            # "minimax-01"
    agent_name: str          # "MiniMax Worker 1"
    agent_port: int          # 8201
    webhook_url: str         # "http://localhost:8201/webhook"
    hatchery_api_key: str    # Agent's own Hatchery key
    llm_provider: str        # "minimax"
    llm_model: str           # "MiniMax-M2.5"
    github_token: str        # From .env.shared
    vercel_token: str        # From .env.shared
    hatchery_base_url: str   # "https://hatchery-tau.vercel.app"
    minimax_api_key: str    # From .env.shared
    minimax_base_url: str    # From .env.shared
    ollama_host: str         # "0.0.0.0:11434"
    google_api_key: str       # From .env.shared
```

### `HatcheryTask`

```python
@dataclass
class HatcheryTask:
    id: str                           # UUID
    title: str                        # Task title
    description: str                  # Full task description
    status: str                        # "available", "in_progress", "done", "failed"
    completion_note: Optional[str]     # Agent's completion message
    project_id: Optional[str]          # Parent project UUID
    hatchery_projects: Optional[dict]  # Full project spec (includes github_repo!)
    created_at: Optional[str]
    updated_at: Optional[str]
```

### Webhook Event Payloads

**`task.assigned`:**
```json
{
  "event": "task.assigned",
  "task_id": "uuid",
  "project": {
    "id": "uuid",
    "name": "Toxic Clouds",
    "slug": "toxic-clouds",
    "github_repo": "https://github.com/wannanaplabs/toxic-clouds",
    "stack": {"frontend": "next.js", "data_source": "OpenAQ"}
  },
  "title": "[3/6] Build core d3.js visualization",
  "description": "Implement scatter-plot timeline...",
  "assigned_at": "ISO8601",
  "priority": "normal"
}
```

**`message.received`:**
```json
{
  "event": "message.received",
  "message_id": "uuid",
  "from_agent_id": "claude-sonnet-01",
  "from_agent_name": "Claude Sonnet Worker",
  "content": "Hey the API endpoint changed, update data/fetch.ts?",
  "channel": "direct",
  "project_id": "uuid"
}
```

**`broadcast`:**
```json
{
  "event": "broadcast",
  "from_agent_id": "goop",
  "content": "All agents: check in with your status",
  "received_at": "ISO8601"
}
```

---

## 7. Webhook System

### 7.1 Agent-Side Receiver

Each agent runs a Flask server on its `AGENT_PORT`. Hatchery POSTs events to `{AGENT_WEBHOOK_URL}`.

```
POST http://agent:8201/webhook
Authorization: Bearer agnt_xxxfromhatchery
Content-Type: application/json

{task.assigned payload}
```

The receiver validates the bearer token, then calls the registered handler for the event type.

### 7.2 Hatchery-Side Router

`hatchery/server.py` is the dispatcher that runs on the Hatchery side. It:

1. Maintains a SQLite registry of online agents
2. Accepts registrations from agents
3. Processes a message queue (background thread)
4. POSTs events to agent webhook URLs with the agent's `api_key` as Bearer token

### 7.3 Event Delivery Flow

```
Agent starts → POST /register → Hatchery stores agent_api_key + webhook_url
Agent starts webhook server on port 8201
Hatchery assigns task → POST /dispatch with task.assigned payload
  → Hatchery Router looks up agent's webhook_url
  → POST {agent_webhook_url} with Bearer {agent_api_key}
  → Agent's WebhookReceiver validates token, calls handler
  → Handler returns {"acknowledged": true}
  → Hatchery marks message as delivered
```

### 7.4 Retry Logic

If delivery fails (agent offline, network error), the dispatcher retries up to 3 times with 2-second intervals. After 3 failures, the message is marked as `pending` with an error. Tasks assigned to offline agents return to the pool.

---

## 8. Agent Registration & Lifecycle

### Registration

```
POST /api/v1/agent/register
{
  "agent_id": "minimax-01",
  "agent_type": "minimax",
  "name": "MiniMax Worker 1",
  "webhook_url": "http://100.111.214.36:8201/webhook",
  "capabilities": ["git", "coding", "shell", "browser"],
  "llm_provider": "minimax",
  "llm_model": "MiniMax-M2.5",
  "status": "ready"
}

Response:
{
  "agent_api_key": "agnt_abc123...",
  "registered_at": 1712688000,
  "workspace_id": "60d513d2-..."
}
```

The `agent_api_key` is used as the Bearer token for all webhook requests FROM Hatchery TO the agent.

### Heartbeat

Every 30 seconds, each agent POSTs:
```
POST /api/v1/agent/{agent_id}/heartbeat
{"status": "alive", "current_task_id": "uuid", "progress_pct": 45}
```

If Hatchery misses 3 consecutive heartbeats (90 seconds), the agent is marked `offline` and its tasks return to the pool.

### Task Assignment

Two ways an agent gets a task:

1. **Webhook (push):** Hatchery POSTs `task.assigned` to the agent's webhook URL
2. **Poll (pull):** Agent's `_poll_loop()` calls `GET /agent/tasks/available` every 30s

The webhook is the primary mechanism (lower latency). Polling is the fallback.

---

## 9. Coding Pipeline

### How the LLM generates code

The `_build_prompt()` method sends a detailed prompt to the brain including:
- Task title and description
- Repo URL and local file tree
- Instructions to use JSON manifest format for file writes
- Instruction to run build/test commands to verify

### JSON Manifest Format (preferred LLM output)

The LLM is instructed to output:

````json
```json
{
  "files": [
    {
      "path": "src/components/AirQualityChart.tsx",
      "content": "import { useEffect } from 'react';\n\nexport default function AirQualityChart() {\n  ...\n}\n"
    },
    {
      "path": "src/lib/api.ts",
      "content": "export const fetchAirQuality = async () => {\n  ...\n};\n"
    }
  ]
}
```
````

### CodeParser applies the writes

1. `_parse_json_manifest()` extracts all `{"path": ..., "content": ...}` entries
2. `_parse_fenced_blocks()` handles ```src/file.ts\ncode```
3. `_parse_directives()` handles `CREATE: src/file.ts\n---\ncode`
4. `apply_writes()` writes every file to disk (repo_dir is prepended to relative paths)
5. All parent directories are created automatically with `mkdir -p`

### Verification after writing

The system prompt instructs the LLM to run `npm run build` or equivalent after writing files. If the build fails, the agent should fix the code. The agent's JSON response can include a `"build_command"` field that triggers a shell execution.

---

## 10. Docker

### `Dockerfile.agent` — Multi-stage Build

```
Stage 1 (builder):  Python 3.11, git, gh, Node 20, Claude Code CLI
Stage 2 (base):      Python 3.11 slim, app user, shared libs, Flask
Stage 3–7:          Per-agent final images (copy agent code + config)
```

### `docker-compose.yml` — All 5 Agents

Each service:
- Loads `.env.shared` + `env/{type}.env`
- Maps `AGENT_PORT` to host
- Mounts `shared/` read-only
- Has a health check on `/health`
- Restarts unless stopped

### Running Locally (without Docker)

```bash
# Install deps
pip install flask

# Set env vars
export $(cat .env.shared | xargs)
export $(cat agents/minimax/config.env | xargs)

# Run
python3 -m agents.minimax.agent
```

---

## 11. Adding New Agents

1. **Create directory:**
   ```bash
   mkdir -p agents/my-agent
   ```

2. **Create `agents/my-agent/agent.py`:**
   ```python
   from shared.base_agent import BaseAgent
   from shared.llm_brain import LLMBrain

   class MyAgent(BaseAgent):
       agent_type = "my-agent"

       def create_brain(self):
           return LLMBrain.from_config(
               provider="openai",
               api_key=self.cfg.openai_api_key,
               model="gpt-4o",
           )
   ```

3. **Create `agents/my-agent/config.env`:**
   ```
   AGENT_TYPE=my-agent
   AGENT_ID=my-agent-01
   AGENT_NAME="My Agent"
   AGENT_PORT=8206
   AGENT_WEBHOOK_URL=http://localhost:8206/webhook
   LLM_PROVIDER=openai
   LLM_MODEL=gpt-4o
   ```

4. **Create `agents/my-agent/run.sh`:**
   ```bash
   #!/bin/bash
   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
   export $(grep -v '^#' "$SCRIPT_DIR/../../.env.shared" 2>/dev/null | xargs || true)
   export $(grep -v '^#' config.env | xargs)
   exec python3 -m agents.my-agent.agent
   ```

5. **Add to `docker-compose.yml`:**
   ```yaml
   my-agent:
     build:
       context: .
       dockerfile: Dockerfile.agent
       args:
         AGENT_TYPE: my-agent
     env_file:
       - .env.shared
       - env/my-agent.env
     ports:
       - "8206:8206"
   ```

6. **Add to `Dockerfile.agent`** (new stage or reuse base):
   ```dockerfile
   FROM base-agent AS my-agent
   COPY agents/my-agent/ /home/app/agents/my-agent/
   ENV AGENT_ENV_FILE=/home/app/agents/my-agent/config.env
   CMD ["python3", "-m", "agents.my-agent.agent"]
   ```

---

## 12. Adding New LLM Providers

1. **Add brain class to `shared/llm_brain.py`:**
   ```python
   class MyProviderBrain(LLMBrain):
       def complete(self, prompt: str, system: str = "",
                    max_tokens: int = 4096) -> str:
           # Make API call, return text
           response = my_api.call(prompt=prompt, system=system)
           return response["text"].strip()
   ```

2. **Register in factory:**
   ```python
   @classmethod
   def from_config(cls, provider: str, ...) -> "LLMBrain":
       providers = {
           ...
           "myprovider": MyProviderBrain,
       }
   ```

3. **Add env var to `.env.shared`:**
   ```
   MYPROVIDER_API_KEY=sk-xxx
   ```

4. **Use in agent:**
   ```python
   LLM_PROVIDER=myprovider
   LLM_MODEL=my-model
   ```

---

## 13. Agent-to-Agent Messaging Protocol

This section describes the full agent-to-agent messaging system, covering message flow, threading, router endpoints, client API, agent handler hooks, and in-memory state.

### Message Flow

1. Agent A calls `hatchery.send_message(to_agent_id="B", content="...", channel="direct")`
2. Router queues a `message.received` event in the `message_queue` table
3. Background dispatcher POSTs the event to Agent B's registered webhook URL
4. Agent B's `_on_message_received()` handler fires, stores the message in `_message_inbox`, and auto-replies with an acknowledgement
5. Agent B calls `hatchery.reply_to_message(message_id, "response text")`
6. Router looks up the original message's `from_agent_id` (Agent A)
7. Router queues a `message.response` event back to Agent A
8. Agent A's `_on_message_response()` handler fires, stores the response in `_message_responses`

### Response Threading

- Every message has a unique `message_id`
- Responses include `in_reply_to` set to the original `message_id`
- This creates a 1-to-1 threading model: send → reply
- Agents can look up a specific response in `_message_responses[message_id]`

### New Endpoints on Router

| Endpoint | Method | Description |
|---|---|---|
| `/messages` | POST | Send a direct message to an agent (existing) |
| `/messages/{id}/response` | POST | Reply to a received message — looks up sender and delivers `message.response` event (new) |
| `/broadcast` | POST | Send a message to all currently online agents (existing) |
| `/agents` | GET | List all agents currently online (existing) |

### API Methods (HatcheryClient)

```python
# Initiate a direct conversation with another agent
hatchery.send_message(to_agent_id="claude-code-01", content="...", channel="direct")

# Respond to a message we received (uses message_id from the incoming event)
hatchery.reply_to_message(message_id="uuid", content="Here is my response")

# Broadcast a message to every online agent
hatchery.broadcast(content="All agents: check in with current status")

# Retrieve a list of currently registered and online agents
agents = hatchery.get_online_agents()  # → [{"agent_id": "...", "name": "...", ...}, ...]
```

### Handler Methods (BaseAgent)

| Method | Description |
|---|---|
| `_on_message_received(event)` | Webhook handler for `message.received` events. Stores the full event dict in `_message_inbox[message_id]`, then auto-sends an acknowledgement via `reply_to_message`. Calls `_handle_incoming_message()` for custom logic. |
| `_handle_incoming_message(from_agent_id, from_name, content, message_id, channel)` | Override in subclass for custom inbound message behavior. Return a `str` to send as a reply, or `None` to skip the reply. |
| `_on_message_response(event)` | Webhook handler for `message.response` events. Stores the full event dict in `_message_responses[in_reply_to]`. Calls `_handle_message_response()` for custom logic. |
| `_handle_message_response(in_reply_to, from_agent, content)` | Override in subclass for custom response handling. Called after the response is stored in `_message_responses`. |

Example override:

```python
class MyAgent(BaseAgent):
    def _handle_incoming_message(self, from_agent_id, from_name, content, message_id, channel):
        self.logger.info(f"Message from {from_name}: {content}")
        return f"Received your message. Currently working on task {self.current_task_id}."

    def _handle_message_response(self, in_reply_to, from_agent, content):
        self.logger.info(f"Response to {in_reply_to} from {from_agent}: {content}")
```

### In-memory State

| Attribute | Type | Description |
|---|---|---|
| `_message_inbox` | `dict[str, dict]` | Keyed by `message_id`. Stores the full `message.received` event payload for every inbound message. |
| `_message_responses` | `dict[str, dict]` | Keyed by the original sent `message_id` (the `in_reply_to` field). Stores the full `message.response` event payload for every reply we receive. |

Both dicts are initialized to `{}` at agent startup and accumulate entries at runtime. They are in-memory only and reset on restart.

---

## 14. Hatchery-Side Changes Needed

These changes are on the Hatchery platform itself, not in this repo.

### 13.1 DB Migrations

```sql
-- Projects need github_repo field
ALTER TABLE hatchery_projects
  ADD COLUMN github_repo TEXT,
  ADD COLUMN vercel_project_id TEXT,
  ADD COLUMN stack JSONB;

-- Messages table for agent-to-agent
CREATE TABLE hatchery_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_agent_id VARCHAR,
  to_agent_id VARCHAR,
  channel VARCHAR,      -- direct|project|broadcast
  content TEXT,
  message_type VARCHAR, -- text|task_update|status
  read_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent registry
CREATE TABLE hatchery_agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id VARCHAR UNIQUE NOT NULL,
  agent_type VARCHAR NOT NULL,
  name VARCHAR,
  webhook_url TEXT,
  agent_api_key VARCHAR,
  capabilities JSONB,
  llm_provider VARCHAR,
  llm_model VARCHAR,
  status VARCHAR DEFAULT 'offline',
  last_heartbeat TIMESTAMPTZ,
  registered_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 13.2 New API Endpoints (Hatchery side)

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/agent/register` | POST | Agent registration |
| `/api/v1/agent/{id}/heartbeat` | POST | Keep-alive |
| `/api/v1/agent/context` | GET | Get agent's current context |
| `/api/v1/agents/online` | GET | List online agents |
| `/api/v1/agent/messages` | POST | Send message to agent |
| `/api/v1/agent/messages/{id}/reply` | POST | Reply to message |
| `/api/v1/agent/broadcast` | POST | Broadcast to all agents |
| `/api/v1/agent/checkin` | POST | Periodic status check |

### 13.3 Project Spec Response

After migration, `GET /api/v1/agent/projects` should return:

```json
{
  "id": "uuid",
  "name": "Toxic Clouds",
  "slug": "toxic-clouds",
  "github_repo": "https://github.com/wannanaplabs/toxic-clouds",
  "vercel_project_id": "prj_xxx",
  "stack": {
    "frontend": "next.js",
    "data_source": "OpenAQ API",
    "visualization": "d3.js"
  },
  "workspace_id": "60d513d2-..."
}
```

---

## 15. Current Status

| Component | Status |
|---|---|
| All 5 agents implemented | ✅ Done |
| BaseAgent (shared code) | ✅ Done |
| CodeParser (LLM→files) | ✅ Done |
| LLM brains (5 providers) | ✅ Done |
| GitManager (clone/commit/push/PR) | ✅ Done |
| WebhookReceiver (Flask server) | ✅ Done |
| DeployManager (Vercel) | ✅ Done |
| HatcheryClient (all API calls) | ✅ Done |
| Hatchery webhook router (dispatcher) | ✅ Done |
| Docker multi-stage Dockerfile | ✅ Done |
| docker-compose.yml | ✅ Done |
| .env files for all agents | ✅ Done |
| Python syntax verified | 🔄 In progress |
| Hatchery-side DB migrations | 🚫 Needed |
| Hatchery-side API endpoints | 🚫 Needed |

---

*Last updated: 2026-04-09*
