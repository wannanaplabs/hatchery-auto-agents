#!/Users/franknguyen/.hermes/hermes-agent/venv/bin/python3
"""
WannanaPlabs Hermes Worker Agent

Uses Hermes AIAgent (MiniMax-M2.7 brain) as the orchestrator.
Delegates actual coding to Claude Code CLI via the terminal tool.

Architecture:
  Hermes (MiniMax, cheap/fast) → plans, orchestrates, verifies
  Claude Code (via terminal) → reads code, writes code, fixes bugs

This replaces the old single-shot agents with a proper agentic loop:
  1. Poll Hatchery for tasks
  2. Claim a task
  3. Have Hermes orchestrate the work (using Claude Code for coding)
  4. Verify the build
  5. Commit, push, update status

Usage:
  python3 hermes_worker.py
"""

import os
import sys
import json
import time
import signal
import logging
import urllib.request
import urllib.error
from pathlib import Path

# Add Hermes to path
HERMES_HOME = Path.home() / ".hermes" / "hermes-agent"
sys.path.insert(0, str(HERMES_HOME))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [hermes-worker] %(levelname)s %(message)s",
)
logger = logging.getLogger("hermes-worker")

# Load env
def load_env(path):
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip('"').strip("'")
        os.environ[k] = v

load_env(Path(__file__).parent / ".env.shared")

# Hatchery API
HATCHERY_BASE = os.environ.get("HATCHERY_BASE_URL", "https://hatchery-tau.vercel.app")
HATCHERY_KEY = os.environ.get("HATCHERY_API_KEY", "")

def hatchery_api(method, path, data=None):
    url = f"{HATCHERY_BASE}/api/v1/{path.lstrip('/')}"
    body = json.dumps(data).encode() if data else None
    headers = {"Authorization": f"Bearer {HATCHERY_KEY}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200] if e.fp else ""}
    except Exception as e:
        return {"_error": str(e)}


def get_available_tasks():
    result = hatchery_api("GET", "agent/tasks/available")
    return result.get("tasks", [])


def claim_task(task_id):
    return hatchery_api("POST", f"agent/tasks/{task_id}/claim")


def update_task_status(task_id, status, comment=""):
    return hatchery_api("PATCH", f"agent/tasks/{task_id}", {"status": status})


def broadcast(content):
    return hatchery_api("POST", "agent/messages", {
        "to_type": "broadcast",
        "message_type": "status_update",
        "content": content,
    })


def run_hermes_agent(task_prompt: str, workdir: str, max_iterations: int = 30) -> str:
    """
    Run the Hermes AIAgent with MiniMax brain + Claude Code terminal tool.
    Returns the conversation result.
    """
    try:
        from run_agent import AIAgent
    except ImportError:
        logger.error("Could not import Hermes AIAgent. Is hermes-agent installed?")
        return "ERROR: Hermes AIAgent not available"

    agent = AIAgent(
        base_url="https://api.minimax.io/anthropic",
        api_key=os.environ.get("MINIMAX_API_KEY", ""),
        model="MiniMax-M2.7",
        max_iterations=max_iterations,
        enabled_toolsets=["terminal", "file"],
        quiet_mode=True,
    )

    system_prompt = f"""You are a WannanaPlabs coding agent. You orchestrate coding tasks by delegating to Claude Code.

RULES:
1. For ALL coding work, use the terminal tool to run Claude Code:
   terminal(command="cd {workdir} && claude -p --dangerously-skip-permissions 'YOUR_TASK_HERE' --model claude-sonnet-4-5", timeout=300)
2. After Claude finishes, ALWAYS verify the build:
   terminal(command="cd {workdir} && npm run build", timeout=120)
3. If build fails, send the error back to Claude to fix:
   terminal(command="cd {workdir} && claude -p --dangerously-skip-permissions 'Fix this build error: ERROR_TEXT' --model claude-sonnet-4-5", timeout=300)
4. When build passes, commit and push:
   terminal(command="cd {workdir} && git add -A && git commit --author='Frank Nguyen <frank.quy.nguyen@gmail.com>' -m 'feat: DESCRIPTION' && git push origin main", timeout=60)
5. NEVER write code yourself — always delegate to Claude Code
6. Report what happened at the end

WORKING DIRECTORY: {workdir}
"""

    try:
        result = agent.run_conversation(
            task_prompt,
            system_prompt=system_prompt,
        )
        # Extract the final assistant message
        if result and hasattr(result, 'messages'):
            for msg in reversed(result.messages):
                if msg.get("role") == "assistant" and msg.get("content"):
                    return msg["content"]
        return str(result)
    except Exception as e:
        logger.error(f"Hermes agent error: {e}")
        return f"ERROR: {e}"


def execute_task(task: dict):
    """Execute a single Hatchery task using the Hermes agent."""
    task_id = task.get("id")
    title = task.get("title", "")
    description = task.get("description", "")
    project = task.get("hatchery_projects", {})
    repo_url = project.get("repo_url", "")
    project_name = project.get("name", "")

    logger.info(f"Executing: {title}")

    # Extract repo slug
    slug = repo_url.rstrip("/").split("/")[-1] if repo_url else "unknown"
    workdir = str(Path.home() / "hatchery-repos" / slug)

    # Clone if needed
    if not Path(workdir).exists():
        os.system(f"git clone --depth 1 {repo_url} {workdir}")
    else:
        os.system(f"cd {workdir} && git pull origin main 2>/dev/null")

    # Build the prompt for Hermes
    prompt = f"""Task: {title}

Description: {description}

Project: {project_name}
Repo: {repo_url}
Working directory: {workdir}

Execute this task by:
1. Clone/pull the repo
2. Delegate the coding to Claude Code via terminal
3. Verify the build passes
4. Commit and push with author "Frank Nguyen <frank.quy.nguyen@gmail.com>"
"""

    # Run the Hermes agent
    result = run_hermes_agent(prompt, workdir)
    logger.info(f"Agent result: {result[:200]}")

    # Update task status
    update_task_status(task_id, "done")
    broadcast(f"Finished: {title} on {project_name}")
    logger.info(f"Task DONE: {title}")


def main():
    logger.info("WannanaPlabs Hermes Worker starting...")
    logger.info(f"Hatchery: {HATCHERY_BASE}")
    logger.info(f"MiniMax model: MiniMax-M2.7")

    running = True

    def shutdown(sig, frame):
        nonlocal running
        logger.info(f"Received {sig}, shutting down...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))

    while running:
        try:
            tasks = get_available_tasks()
            if tasks:
                task = tasks[0]
                logger.info(f"Picked up: {task.get('title', '?')}")
                claim_result = claim_task(task["id"])
                if "_error" not in claim_result:
                    execute_task(task)
                else:
                    logger.warning(f"Claim failed: {claim_result}")
            else:
                logger.debug("No tasks available")
        except Exception as e:
            logger.error(f"Worker error: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
