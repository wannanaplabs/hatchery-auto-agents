"""Hatchery API client — all calls to the Hatchery platform."""
import os
import urllib.request
import urllib.error
import json
import time
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

class HatcheryClient:
    """Thin wrapper around Hatchery REST API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("HATCHERY_BASE_URL")
                        or "https://hatchery-tau.vercel.app")
        self.api_key = api_key or os.environ.get("HATCHERY_API_KEY", "")
        if not self.api_key:
            raise ValueError("HATCHERY_API_KEY not set")

    def _request(self, method: str, path: str, data: Optional[dict] = None,
                 timeout: int = 30) -> dict:
        url = f"{self.base_url}/api/v1/{path.lstrip('/')}"
        body = json.dumps(data).encode() if data else None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            logger.error(f"HTTP {e.code} on {method} {path}: {body[:200]}")
            raise

    # -----------------------------------------------------------------
    # Agent Registry
    # -----------------------------------------------------------------

    def register(self, agent_config: "AgentConfig") -> dict:
        """Register agent with Hatchery. Returns agent_api_key."""
        return self._request("POST", "agent/register", {
            "agent_id": agent_config.agent_id,
            "agent_type": agent_config.agent_type,
            "name": agent_config.agent_name,
            "webhook_url": agent_config.webhook_url,
            "capabilities": ["git", "coding", "shell", "browser"],
            "llm_provider": agent_config.llm_provider,
            "llm_model": agent_config.llm_model,
            "status": "ready",
        })

    def heartbeat(self, agent_id: str, status: str = "alive",
                  current_task_id: Optional[str] = None,
                  progress_pct: Optional[int] = None) -> dict:
        return self._request("POST", f"agent/{agent_id}/heartbeat", {
            "status": status,
            "current_task_id": current_task_id,
            "progress_pct": progress_pct,
        })

    # -----------------------------------------------------------------
    # Tasks
    # -----------------------------------------------------------------

    def get_available_tasks(self) -> list[dict]:
        data = self._request("GET", "agent/tasks/available")
        return data.get("tasks", [])

    def claim_task(self, task_id: str) -> dict:
        return self._request("POST", f"agent/tasks/{task_id}/claim")

    def update_task_status(self, task_id: str, status: str,
                           comment: Optional[str] = None,
                           progress_pct: Optional[int] = None) -> dict:
        body = {"status": status}
        if comment:
            body["completion_note"] = comment
        if progress_pct is not None:
            body["progress_pct"] = progress_pct
        return self._request("PATCH", f"agent/tasks/{task_id}", body)

    def get_context(self) -> dict:
        """Get current agent context (current task, workspace state)."""
        return self._request("GET", "agent/context")

    # -----------------------------------------------------------------
    # Messaging
    # -----------------------------------------------------------------

    def send_message(self, to_agent_id: str, content: str,
                     message_type: str = "fyi",
                     requires_ack: bool = False,
                     parent_message_id: str | None = None,
                     project_id: str | None = None,
                     task_id: str | None = None) -> dict:
        """
        Send a message to another agent via the Hatchery platform API.
        
        Args:
            to_agent_id: Target agent ID
            content: Message content
            message_type: One of "handoff", "question", "blocker", "fyi", "status_update"
            requires_ack: Whether to request an acknowledgment response
            parent_message_id: If replying to a thread, the parent message ID
            project_id: Optional project context
            task_id: Optional task context
        """
        return self._request("POST", "agent/messages", {
            "to_type": "agent",
            "to_agent_id": to_agent_id,
            "message_type": message_type,
            "content": content,
            "requires_ack": requires_ack,
            "parent_message_id": parent_message_id,
            "project_id": project_id,
            "task_id": task_id,
        })

    def reply_to_message(self, message_id: str, response: str) -> dict:
        """
        Acknowledge/respond to a message received from another agent.
        Uses the acknowledge endpoint with the response text.
        """
        return self._request("POST", f"agent/messages/{message_id}/acknowledge", {
            "response": response,
        })

    def broadcast(self, content: str, message_type: str = "fyi") -> dict:
        """
        Broadcast a message to all online agents in the workspace.
        """
        return self._request("POST", "agent/messages", {
            "to_type": "broadcast",
            "message_type": message_type,
            "content": content,
            "requires_ack": False,
        })

    def get_online_agents(self) -> list:
        """
        List all registered agents in the workspace.
        """
        data = self._request("GET", "agent/agents")
        return data.get("agents", [])

    def get_messages(self) -> list:
        """
        Fetch unread messages for this agent.
        """
        data = self._request("GET", "agent/messages")
        return data.get("messages", [])

    def get_thread(self, thread_id: str) -> list:
        """
        Get all messages in a conversation thread.
        """
        data = self._request("GET", f"agent/messages/threads/{thread_id}")
        return data.get("messages", [])

    def checkin(self, agent_id: str, status: str,
                task_id: Optional[str] = None,
                progress_pct: Optional[int] = None) -> dict:
        body = {"status": status}
        if task_id:
            body["task_id"] = task_id
        if progress_pct is not None:
            body["progress_pct"] = progress_pct
        return self._request("POST", f"agent/checkin", body)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
if TYPE_CHECKING:
    from .types import AgentConfig
