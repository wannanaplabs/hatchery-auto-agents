"""Shared utilities for Hatchery autonomous agents."""
import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional

def setup_logging(name: str = "hatchery-agent", level: int = logging.INFO):
    """Configure structured logging."""
    logging.basicConfig(
        level=level,
        format=f"%(asctime)s [{name}] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

def load_env_file(path: str | Path):
    """Parse a .env file and set environment variables."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f".env file not found: {path}")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ[key.strip()] = val.strip()

def load_shared_env(env_dir: str | Path = "."):
    """Load .env.shared and set env vars."""
    shared = Path(env_dir) / ".env.shared"
    if shared.exists():
        load_env_file(shared)

def ensure_dir(path: str | Path) -> Path:
    """Ensure directory exists, return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def read_json(path: str | Path) -> dict:
    """Read a JSON file."""
    with open(Path(path)) as f:
        return json.load(f)

def write_json(path: str | Path, data: dict):
    """Write a JSON file."""
    with open(Path(path), "w") as f:
        json.dump(data, f, indent=2)

def task_context_path(agent_id: str) -> Path:
    """Return path to the task context file for an agent."""
    base = Path.home() / ".hatchery-agents" / agent_id
    base.mkdir(parents=True, exist_ok=True)
    return base / "task_context.json"

def save_task_context(agent_id: str, task_id: str, step: str, data: dict):
    """Save progress on a progressive task."""
    write_json(task_context_path(agent_id), {
        "task_id": task_id,
        "step": step,
        "data": data,
    })

def load_task_context(agent_id: str) -> Optional[dict]:
    """Load task context if it exists."""
    ctx = task_context_path(agent_id)
    if ctx.exists():
        return read_json(ctx)
    return None

def clear_task_context(agent_id: str):
    """Clear task context after completion."""
    ctx = task_context_path(agent_id)
    if ctx.exists():
        ctx.unlink()
