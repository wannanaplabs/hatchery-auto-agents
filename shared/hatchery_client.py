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
            # 429 rate-limit is expected and handled by callers — log at DEBUG
            # to avoid spam. 400/401/500/etc. are real errors, log at ERROR.
            if e.code == 429:
                logger.debug(f"HTTP 429 on {method} {path}: {body[:200]}")
            else:
                logger.error(f"HTTP {e.code} on {method} {path}: {body[:200]}")
            # Attach the body to the exception so callers can inspect it
            e.response_body = body
            raise

    # -----------------------------------------------------------------
    # Agent Registry
    # -----------------------------------------------------------------

    def register(self, agent_config: "AgentConfig") -> dict:
        """Register agent webhook with Hatchery platform. Returns webhook config."""
        return self._request("PUT", "agent/webhook", {
            "url": agent_config.webhook_url,
            "event_types": [
                "message.received", "task.assigned", "conflict.raised",
                "ack.required", "human.responded",
            ],
        })

    def heartbeat(self, agent_id: str, status: str = "alive",
                  current_task_id: Optional[str] = None,
                  progress_pct: Optional[int] = None) -> dict:
        return self._request("POST", "agent/checkin", {
            "status": status,
            "task_id": current_task_id,
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

    def reset_session(self) -> dict:
        """Reset the agent session by calling GET /context (resets iteration counter)."""
        try:
            data = self._request("GET", "agent/context")
            logger.info("Session reset successfully")
            return data
        except Exception as e:
            logger.warning(f"Session reset failed: {e}")
            return {}

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

    def get_notifications(self) -> list[dict]:
        """
        Poll for pending webhook deliveries (notifications) that couldn't be
        delivered directly (e.g. agent behind NAT). Call every 30s.
        Returns list of notification objects with event type + payload.
        """
        data = self._request("GET", "agent/notifications")
        return data.get("notifications", [])

    def acknowledge_notification(self, delivery_id: str,
                                   response: str = "",
                                   status: str = "acknowledged") -> dict:
        """
        Acknowledge a webhook notification. For message.received events,
        the response is forwarded to the originating agent as a reply.
        """
        return self._request(
            "POST",
            f"agent/webhooks/{delivery_id}/acknowledge",
            {"response": response, "status": status}
        )

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
