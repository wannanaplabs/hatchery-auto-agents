"""Shared types for Hatchery autonomous agents."""
from dataclasses import dataclass, field
from typing import Optional, Literal

# -------------------------------------------------------------------
# Webhook Event Types
# -------------------------------------------------------------------

@dataclass
class ProjectSpec:
    id: str
    name: str
    slug: str
    github_repo: str
    stack: dict = field(default_factory=dict)
    vercel_project_id: Optional[str] = None

@dataclass
class TaskAssignedEvent:
    event: Literal["task.assigned"]
    task_id: str
    project: ProjectSpec
    title: str
    description: str
    assigned_at: str
    priority: Literal["high", "normal", "low"] = "normal"
    deadline: Optional[str] = None

@dataclass
class MessageReceivedEvent:
    event: Literal["message.received"]
    message_id: str
    from_agent_id: str
    from_agent_name: str
    content: str
    channel: Literal["direct", "project", "broadcast"]
    project_id: Optional[str] = None
    in_reply_to: Optional[str] = None  # message_id this is replying to

@dataclass
class MessageResponseEvent:
    event: Literal["message.response"]
    in_reply_to: str
    from_agent_id: str
    from_agent_name: str
    content: str

@dataclass
class BroadcastEvent:
    event: Literal["broadcast"]
    from_agent_id: str
    content: str
    received_at: str

@dataclass
class TaskUpdatedEvent:
    event: Literal["task.updated"]
    task_id: str
    updated_by: str
    changes: dict
    project_id: str

@dataclass
class TaskTransferredEvent:
    event: Literal["task.transferred"]
    task_id: str
    from_agent_id: str
    reason: str
    project: ProjectSpec

# Union of all event types for parsing
WebhookEvent = (
    TaskAssignedEvent | MessageReceivedEvent | MessageResponseEvent |
    BroadcastEvent | TaskUpdatedEvent | TaskTransferredEvent | dict
)

# -------------------------------------------------------------------
# Agent Config
# -------------------------------------------------------------------

@dataclass
class AgentConfig:
    agent_type: str
    agent_id: str
    agent_name: str
    agent_port: int
    webhook_url: str
    hatchery_api_key: str
    llm_provider: str
    llm_model: str
    # Shared (loaded from .env.shared)
    github_token: str = ""
    vercel_token: str = ""
    hatchery_base_url: str = "https://hatchery-tau.vercel.app"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.chat/v1"
    ollama_host: str = "0.0.0.0:11434"
    google_api_key: str = ""

    @classmethod
    def from_env(cls, agent_env_file: Optional[str] = None):
        """Load config from environment variables."""
        import os
        cfg = cls(
            agent_type=os.environ["AGENT_TYPE"],
            agent_id=os.environ["AGENT_ID"],
            agent_name=os.environ.get("AGENT_NAME", os.environ["AGENT_ID"]),
            agent_port=int(os.environ["AGENT_PORT"]),
            webhook_url=os.environ["AGENT_WEBHOOK_URL"],
            hatchery_api_key=os.environ["HATCHERY_API_KEY"],
            llm_provider=os.environ["LLM_PROVIDER"],
            llm_model=os.environ["LLM_MODEL"],
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            vercel_token=os.environ.get("VERCEL_TOKEN", ""),
            hatchery_base_url=os.environ.get("HATCHERY_BASE_URL", "https://hatchery-tau.vercel.app"),
            minimax_api_key=os.environ.get("MINIMAX_API_KEY", ""),
            minimax_base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.chat/v1"),
            ollama_host=os.environ.get("OLLAMA_HOST", "0.0.0.0:11434"),
            google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        )
        return cfg

# -------------------------------------------------------------------
# Hatchery API Shapes
# -------------------------------------------------------------------

@dataclass
class HatcheryTask:
    id: str
    title: str
    description: str
    status: str
    completion_note: Optional[str] = None
    project_id: Optional[str] = None
    hatchery_projects: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class AgentRegistration:
    agent_id: str
    agent_type: str
    name: str
    webhook_url: str
    capabilities: list[str] = field(default_factory=lambda: ["git", "coding", "shell"])
    llm_provider: str = ""
    llm_model: str = ""
