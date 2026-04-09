# Hatchery Auto-Agents — Developer Guide

For AI coding assistants working on this codebase. Start here before making changes.

---

## Quick Start

```bash
cd ~/hatchery-auto-agents

# 1. Copy and fill in secrets
cp .env.shared .env.shared.real
# Edit .env.shared.real with real values, then:
export $(cat .env.shared.real | xargs)

# 2. Run locally (no Docker needed)
pip install flask
python3 -m agents.minimax.agent
```

---

## Project Map

```
hatchery-auto-agents/
├── SPEC.md                     ← Full technical reference (types, API, architecture)
├── CLAUDE.md                   ← This file — developer guide
├── README.md                   ← Usage overview
│
├── .env.shared                 ← Shared secrets (NEVER commit real values)
│
├── docker-compose.yml           ← All 5 agents via Docker
├── Dockerfile.agent             ← Multi-stage build (one Dockerfile for all agents)
│
├── env/                         ← Per-agent env stubs (copy to real values)
│   ├── minimax.env
│   ├── claude-code.env
│   ├── qwen.env
│   ├── deepseek.env
│   └── gemma.env
│
├── shared/                      ← All shared code (imported by every agent)
│   ├── base_agent.py            ← BaseAgent class + CodeParser
│   ├── hatchery_client.py        ← HatcheryClient (Hatchery API calls)
│   ├── llm_brain.py              ← LLMBrain factory + all providers
│   ├── git_manager.py            ← GitManager (clone/commit/push/PR)
│   ├── webhook_receiver.py       ← WebhookReceiver (Flask webhook server)
│   ├── deploy_manager.py         ← DeployManager (Vercel deploy)
│   ├── types.py                  ← Dataclasses (AgentConfig, events, tasks)
│   └── utils.py                  ← Logging, env loading, JSON helpers
│
├── agents/                      ← One subdir per agent type
│   ├── minimax/
│   │   ├── agent.py              ← MinimaxAgent(BaseAgent)
│   │   ├── config.env            ← Per-agent config
│   │   └── run.sh                ← Startup script
│   ├── claude-code/
│   │   ├── agent.py              ← ClaudeCodeAgent(BaseAgent)
│   │   ├── config.env
│   │   └── run.sh
│   ├── qwen/
│   │   ├── agent.py              ← QwenAgent(BaseAgent)
│   │   ├── config.env
│   │   └── run.sh
│   ├── deepseek/
│   │   ├── agent.py              ← DeepSeekAgent(BaseAgent)
│   │   ├── config.env
│   │   └── run.sh
│   └── gemma/
│       ├── agent.py              ← GemmaAgent(BaseAgent)
│       ├── config.env
│       └── run.sh
│
├── hatchery/                    ← Hatchery-side webhook router
│   ├── server.py                ← Flask app: register, dispatch, queue
│   └── run.sh                   ← Startup script
│
└── tests/                       ← Basic smoke tests
```

---

## Key Patterns

### Adding a New Agent

Minimum viable agent:

```python
# agents/new/agent.py
from shared.base_agent import BaseAgent
from shared.llm_brain import LLMBrain

class NewAgent(BaseAgent):
    agent_type = "new"

    def create_brain(self):
        return LLMBrain.from_config(
            provider="openai",        # must match a provider in llm_brain.py
            api_key=self.cfg.openai_api_key,
            model="gpt-4o",
        )
```

```bash
# agents/new/config.env
AGENT_TYPE=new
AGENT_ID=new-01
AGENT_PORT=8206
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
```

Then add to `docker-compose.yml` and `Dockerfile.agent`.

### Adding a New LLM Provider

1. Subclass `LLMBrain` in `shared/llm_brain.py`:

```python
class MyProviderBrain(LLMBrain):
    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 4096) -> str:
        # Call your API here
        response = my_api.post(prompt=prompt, system=system)
        return response["choices"][0]["message"]["content"].strip()
```

2. Register it in the factory:

```python
@classmethod
def from_config(cls, provider: str, api_key: str, model: str, **kwargs):
    providers = {
        "minimax": MiniMaxBrain,
        "ollama": OllamaBrain,
        "google": GeminiBrain,
        "anthropic": ClaudeCodeBrain,
        "openai": OpenAIBrain,
        "myprovider": MyProviderBrain,   # ← add here
    }
    if provider not in providers:
        raise ValueError(...)
    return providers[provider](api_key=api_key, model=model, **kwargs)
```

3. Add API key to `.env.shared`: `MYPROVIDER_API_KEY=...`

4. Set `LLM_PROVIDER=myprovider` in the agent's config.env.

### Modifying Task Execution

To change how agents execute tasks, edit `BaseAgent._execute_task()` in `shared/base_agent.py`. This is the method that:
1. Claims the task
2. Clones the repo
3. Calls the brain
4. Parses code
5. Commits and pushes
6. Deploys (optional)
7. Opens PR (optional)
8. Marks task done

To add a new step (e.g., run tests after commit), add it in `_execute_task()`:

```python
def _execute_task(self, task: dict):
    ...
    self._commit_and_push(commit_msg, task_id)

    # NEW: run test suite
    test_result = self._run_tests(repo_dir)

    if not test_result["ok"]:
        self.hatchery.update_task_status(task_id, "failed",
            comment=f"Tests failed: {test_result['output']}")
        return
    ...
```

### Webhook Event Handling

To add a new webhook event type:

1. Add handler method in `BaseAgent`:
```python
def _on_my_event(self, event: dict) -> dict:
    logger.info(f"Got my event: {event}")
    return {"acknowledged": True}
```

2. Register it in `run()`:
```python
self.webhook = WebhookReceiver(
    port=self.cfg.agent_port,
    agent_api_key=self.agent_api_key,
    event_handlers={
        "task.assigned": self._on_task_assigned,
        "message.received": self._on_message_received,
        "my_event": self._on_my_event,   # ← add here
    },
)
```

3. Hatchery will POST with `{"event": "my_event", ...}`.

---

## How to Test

### Local smoke test (no Docker)

```bash
# Test hatchery client
cd ~/hatchery-auto-agents
export $(cat .env.shared | xargs)
python3 -c "
import sys; sys.path.insert(0, '.')
from shared.hatchery_client import HatcheryClient
c = HatcheryClient()
print('Tasks:', len(c.get_available_tasks()))
"

# Test git manager
python3 -c "
import sys; sys.path.insert(0, '.')
from shared.git_manager import GitManager
g = GitManager(github_token='test')
print('GitManager created OK')
"

# Test code parser
python3 -c "
import sys; sys.path.insert(0, '.')
from shared.base_agent import CodeParser
from pathlib import Path
result = CodeParser.parse('\`\`\`json\n{\"files\":[{\"path\":\"x.txt\",\"content\":\"hi\"}]}\n\`\`\`', Path('/tmp'))
print('Parsed:', list(result.keys()))
"
```

### Test inside Docker

```bash
docker compose build minimax-agent
docker compose run --rm minimax-agent python3 -c "from shared.hatchery_client import HatcheryClient; print('OK')"
```

---

## Common Tasks

### Debug an agent inside its container

```bash
docker compose exec minimax-agent /bin/bash
# Inside container:
python3 -c "
import sys; sys.path.insert(0, '/home/app')
from shared.hatchery_client import HatcheryClient
c = HatcheryClient()
print(c.get_available_tasks())
"
```

### Check which agents are registered

```bash
# Via Hatchery API
curl https://hatchery-tau.vercel.app/api/v1/agents \
  -H "Authorization: Bearer $HATCHERY_API_KEY"

# Via local router DB
sqlite3 /tmp/hatchery-router.db "SELECT agent_id, status, last_seen FROM agents;"
```

### Manually trigger a task dispatch

```bash
curl -X POST http://localhost:8090/dispatch \
  -H "Authorization: Bearer agnt_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "task.assigned",
    "target": "minimax-01",
    "payload": {
      "event": "task.assigned",
      "task_id": "test-123",
      "title": "Test task",
      "description": "Hello world"
    }
  }'
```

### Simulate a webhook to an agent

```bash
curl -X POST http://localhost:8201/webhook \
  -H "Authorization: Bearer agnt_from_registration" \
  -H "Content-Type: application/json" \
  -d '{"event":"task.assigned","task_id":"test-123","title":"Test"}'
```

### Force restart an agent

```bash
docker compose restart minimax-agent
# Or without Docker:
pkill -f "python3 -m agents.minimax.agent"
python3 -m agents.minimax.agent &
```

---

## Configuration Priority

Environment variables are loaded in this order (later overwrites earlier):

1. `.env.shared` (shared secrets)
2. `env/{type}.env` (per-agent stubs — has AGENT_TYPE, AGENT_PORT, etc.)
3. `agents/{type}/config.env` (runtime config — what `run.sh` loads)
4. `AGENT_ENV_FILE` env var pointing to a custom env file

This means you can override any setting at runtime without changing files.

---

## Ports

| Agent | Port | Webhook URL |
|---|---|---|
| minimax-agent | 8201 | http://localhost:8201/webhook |
| claude-code-agent | 8202 | http://localhost:8202/webhook |
| qwen-agent | 8203 | http://localhost:8203/webhook |
| deepseek-agent | 8204 | http://localhost:8204/webhook |
| gemma-agent | 8205 | http://localhost:8205/webhook |
| hatchery-router | 8090 | N/A (runs Hatchery-side) |

---

## File Watching / Hot Reload

The agents do **not** support hot reload. To update an agent:
1. Update the code
2. Rebuild the Docker image: `docker compose build <agent-name>`
3. Restart: `docker compose up -d <agent-name>`

Without Docker, just restart the Python process.

---

## Troubleshooting

### "HTTP 403 on /webhook"

The `agent_api_key` returned by Hatchery at registration time is wrong or expired. Re-register:

```python
# In Python
client = HatcheryClient()
resp = client.register(my_config)
print(resp['agent_api_key'])  # Use this as Bearer token
```

### "No module named 'shared'"

The agent isn't running from the right directory. `sys.path` must include the `shared/` parent directory. The `run.sh` scripts handle this automatically. If running manually:

```bash
cd ~/hatchery-auto-agents
python3 -m agents.minimax.agent
```

### "Git clone failed: authentication required"

The GitHub token isn't stored in the credential helper. `GitManager.__init__()` writes to `~/.git-credentials`, but Docker containers have a different home directory. Mount a volume or set `HOME=/root` in the container.

### "Ollama connection refused" (Qwen/DeepSeek agents)

Ollama isn't running on the expected host. Check:
```bash
curl http://0.0.0.0:11434/api/tags  # Should list available models
```
If Ollama is on a different host, set `OLLAMA_HOST=192.168.x.x:11434` in `.env.shared`.

### "MiniMax API error 429"

Rate limited. The agent will retry on next poll cycle (30s). If persistent, the brain's `complete()` method has no built-in retry — add one:

```python
def complete(self, prompt, system="", max_tokens=4096):
    for attempt in range(3):
        try:
            return self._call(prompt, system, max_tokens)
        except RateLimitError:
            time.sleep(2 ** attempt)
    raise RuntimeError("MiniMax rate limited after 3 attempts")
```

---

## Architecture Decisions

### Why a base class instead of composition?
Because agents need to override `create_brain()` cleanly. A mixin or strategy pattern would work too, but inheritance is the simplest that maintains readability.

### Why CodeParser instead of letting the LLM write files directly?
Agents run in containers with limited filesystem access. CodeParser gives us a clean, auditable layer between LLM output and filesystem writes. It also handles malformed output gracefully.

### Why polling + webhooks instead of just webhooks?
Webhooks are the primary mechanism (push = low latency). Polling is a fallback if webhooks fail or during development. Both paths use the same `_execute_task()` pipeline.

### Why SQLite for the Hatchery router?
It's a simple, embedded, zero-config store. For production with many agents, replace with PostgreSQL. The interface is identical — just swap the `get_db()` function.

---

*Keep SPEC.md updated when changing architecture. Keep CLAUDE.md updated when changing developer workflows.*
