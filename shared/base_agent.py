"""
Base agent class — shared logic for all Hatchery agent types.

Each agent (minimax, claude-code, qwen, deepseek, gemma) inherits from
BaseAgent and only overrides:
  - brain property (which LLM to use)
  - agent_type (string identifier)
  - optionally: system_prompt

Everything else — git, Hatchery API, webhook handling, task execution,
code parsing, deploy, heartbeat — is shared.
"""
from __future__ import annotations

import os
import sys
import re
import time
import json
import logging
import signal
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable, Any

# Ensure shared/ is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.hatchery_client import HatcheryClient
from shared.webhook_receiver import WebhookReceiver
from shared.git_manager import GitManager
from shared.deploy_manager import DeployManager
from shared.types import AgentConfig
from shared.utils import (
    setup_logging, load_env_file, load_shared_env,
    save_task_context, clear_task_context, read_json, write_json,
    ensure_dir,
)

logger = logging.getLogger("base-agent")


# -----------------------------------------------------------------------
# Code Parsing — parse LLM output into file writes
# -----------------------------------------------------------------------

class CodeParser:
    """
    Parses LLM markdown output into structured file writes.

    Supports three formats:

    1. Fenced code blocks with path in language tag:
       ```src/app.ts
       const x = 1;
       ```

    2. JSON manifest (preferred — unambiguous):
       ```json
       {
         "files": [
           {"path": "src/app.ts", "content": "const x = 1;\n"},
           {"path": "src/utils.ts", "content": "..."}
         ]
       }
       ```

    3. Inline directives:
       CREATE: src/app.ts
       ---
       const x = 1;

    Returns a list of (relative_path: str, content: str) tuples.
    """

    @classmethod
    def parse(cls, text: str, repo_dir: Path) -> dict[Path, str]:
        """
        Parse LLM output and return {Path: content} dict of files to write.
        Paths are absolute (repo_dir / relative_path).

        Robust to:
        - Reasoning models that emit `<think>...</think>` blocks (stripped)
        - Bare JSON manifests not wrapped in ```json fences
        - Mixed formats in the same response
        """
        # Strip reasoning/think blocks from models like DeepSeek-R1, Qwen3-thinking, MiniMax M2.5
        text = cls._strip_thinking_blocks(text)

        writes: dict[Path, str] = {}

        # 1. JSON manifest inside ```json fence (preferred)
        writes.update(cls._parse_json_manifest(text, repo_dir))

        # 2. Bare JSON manifest (no fence — reasoning models often do this)
        if not writes:
            writes.update(cls._parse_bare_json_manifest(text, repo_dir))

        # 3. Fenced code blocks with path in language tag
        fence_writes = cls._parse_fenced_blocks(text, repo_dir)
        # Only merge fence writes if they don't collide with json manifest
        for p, c in fence_writes.items():
            if p not in writes:
                writes[p] = c

        # 4. CREATE: /path directives
        directive_writes = cls._parse_directives(text, repo_dir)
        for p, c in directive_writes.items():
            if p not in writes:
                writes[p] = c

        return writes

    @staticmethod
    def _strip_thinking_blocks(text: str) -> str:
        """
        Remove <think>...</think>, <thinking>...</thinking>, and similar
        reasoning blocks that many reasoning models emit before their answer.
        """
        # Match <think> or <thinking> blocks (with any case)
        patterns = [
            r"<think(?:ing)?>.*?</think(?:ing)?>",
            # Occasionally models leave an unclosed <think> block at the start
            r"^<think(?:ing)?>.*?(?=\n\s*[{\[`])",
        ]
        for pat in patterns:
            text = re.sub(pat, "", text, flags=re.DOTALL | re.IGNORECASE)
        return text.strip()

    @classmethod
    def _parse_json_manifest(cls, text: str, repo_dir: Path) -> dict[Path, str]:
        """Parse ```json ... { "files": [...] } ``` blocks."""
        writes: dict[Path, str] = {}
        pattern = re.compile(r"```json\s*(.+?)\s*```", re.DOTALL)
        for m in pattern.finditer(text):
            json_text = m.group(1).strip()
            writes.update(cls._load_manifest_json(json_text, repo_dir))
        return writes

    @classmethod
    def _parse_bare_json_manifest(cls, text: str, repo_dir: Path) -> dict[Path, str]:
        """
        Parse a raw JSON manifest that isn't wrapped in a code fence.
        Common with reasoning models that just dump `{"files": [...]}` directly.

        Finds the first balanced JSON object that contains a "files" key.
        """
        writes: dict[Path, str] = {}
        # Find the first `{` that starts a potential JSON object
        for start in range(len(text)):
            if text[start] != "{":
                continue
            # Walk forward to find the matching close brace
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\" and in_string:
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        # Cheap pre-check to avoid parsing huge irrelevant blobs
                        if '"files"' in candidate:
                            loaded = cls._load_manifest_json(candidate, repo_dir)
                            if loaded:
                                writes.update(loaded)
                                return writes  # First successful match wins
                        break
        return writes

    @classmethod
    def _load_manifest_json(cls, json_text: str, repo_dir: Path) -> dict[Path, str]:
        """
        Load a JSON string into file writes.
        Returns {} if the JSON is invalid or missing required fields.
        """
        writes: dict[Path, str] = {}
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            return writes
        if not isinstance(data, dict):
            return writes
        files = data.get("files", [])
        if not isinstance(files, list):
            return writes
        for f in files:
            if not isinstance(f, dict):
                continue
            rel = f.get("path")
            if not rel or not isinstance(rel, str):
                continue
            # Reject absolute paths and path traversal attempts
            if rel.startswith("/") or ".." in Path(rel).parts:
                continue
            try:
                path = repo_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                content = f.get("content", "")
                if not isinstance(content, str):
                    content = str(content)
                if f.get("encrypted"):
                    content = cls._decrypt(content, os.environ.get("CODE_CIPHER", ""))
                writes[path] = content
            except OSError:
                continue
        return writes

    @classmethod
    def _parse_fenced_blocks(cls, text: str, repo_dir: Path) -> dict[Path, str]:
        """Parse ```language\ncontent``` blocks for code files."""
        writes: dict[Path, str] = {}
        # Match ```path/to/file.ext\ncontent```
        # or just ```\ncontent``` (no path — skip)
        pattern = re.compile(
            r"```(\S[^\n]*)\n(.*?)```",
            re.DOTALL
        )
        for m in pattern.finditer(text):
            lang_or_path = m.group(1).strip()
            content = m.group(2)

            # Skip if it looks like a language (single short word, no /)
            if lang_or_path and "/" not in lang_or_path and not Path(lang_or_path).suffix:
                continue  # Probably a language identifier like "python", "json"

            # Try to extract path from lang_or_path
            # Could be: "src/app.ts", "agents/minimax/agent.py:10", etc.
            path_str = lang_or_path.split(":")[0].strip()
            if not path_str:
                continue

            # Validate it looks like a file path
            if not re.search(r"\.\w+$", path_str):
                # No extension — skip unless it looks like a known config file
                if path_str not in (".env.example", "Dockerfile", "Makefile", ".gitignore"):
                    continue

            path = repo_dir / path_str
            path.parent.mkdir(parents=True, exist_ok=True)
            writes[path] = content.strip() + "\n"

        return writes

    @classmethod
    def _parse_directives(cls, text: str, repo_dir: Path) -> dict[Path, str]:
        """Parse CREATE:/path ---\ncontent blocks."""
        writes: dict[Path, str] = {}
        pattern = re.compile(r"CREATE:\s*([^\s]+)\s*---(.*?)(?=CREATE:|$)", re.DOTALL)
        for m in pattern.finditer(text):
            path_str = m.group(1).strip()
            content = m.group(2).strip()
            path = repo_dir / path_str
            path.parent.mkdir(parents=True, exist_ok=True)
            writes[path] = content + "\n"
        return writes

    @staticmethod
    def _decrypt(content: str, cipher: str) -> str:
        """Simple XOR decryption for sensitive code (optional layer)."""
        if not cipher or not content:
            return content
        try:
            key = cipher.encode()
            return "".join(
                chr(b ^ key[i % len(key)])
                for i, b in enumerate(content.encode())
            )
        except Exception:
            return content

    @classmethod
    def apply_writes(cls, writes: dict[Path, str], dry_run: bool = False) -> list[str]:
        """
        Write parsed files to disk.
        Returns list of written file paths (as strings).
        """
        written = []
        for path, content in writes.items():
            if dry_run:
                logger.info(f"[DRY RUN] Would write: {path} ({len(content)} bytes)")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                logger.info(f"Wrote: {path}")
            written.append(str(path))
        return written


# -----------------------------------------------------------------------
# Base Agent
# -----------------------------------------------------------------------

class BaseAgent:
    """
    Shared agent implementation.

    Subclass and override:
      - brain (property returning an LLMBrain)
      - agent_type (str, e.g. "minimax", "claude-code")
      - system_prompt (str, optional)

    Usage:
        class MyAgent(BaseAgent):
            @property
            def agent_type(self) -> str: return "my-agent"
            def create_brain(self) -> LLMBrain:
                return MiniMaxBrain(api_key=..., model="...")

        MyAgent().run()
    """

    # Override in subclass
    agent_type: str = "base"
    capabilities: list[str] = []  # Set per agent — used for task routing
    system_prompt: str = (
        "You are a precise autonomous coding agent. "
        "Analyze the task, implement the code, and report changes clearly."
    )

    def __init__(self, config: Optional[AgentConfig] = None,
                 env_file: Optional[str] = None):
        """
        Initialize the agent.

        Args:
            config: AgentConfig. If None, loads from environment.
            env_file: Path to per-agent .env file (e.g. agents/minimax/config.env).
                     If provided, loads it before building the config.
        """
        # Load env files
        base_dir = Path(__file__).parent.parent
        load_shared_env(base_dir)
        if env_file:
            load_env_file(env_file)
        elif os.environ.get("AGENT_ENV_FILE"):
            load_env_file(os.environ["AGENT_ENV_FILE"])

        self.cfg = config or AgentConfig.from_env()
        self.hatchery = HatcheryClient(
            api_key=self.cfg.hatchery_api_key,
            base_url=self.cfg.hatchery_base_url,
        )
        self.git = GitManager(
            github_token=self.cfg.github_token,
            author_name=os.environ.get("GIT_AUTHOR_NAME", "Hatchery Agent"),
            author_email=os.environ.get("GIT_AUTHOR_EMAIL", "agent@hatchery.local"),
        )
        self.deploy = DeployManager(
            vercel_token=self.cfg.vercel_token,
            github_token=self.cfg.github_token,
        )
        self.brain = self.create_brain()

        self.webhook: Optional[WebhookReceiver] = None
        self.agent_api_key: str = ""
        self.running = False
        self.current_task_id: Optional[str] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        # Interruptible sleep — set on shutdown so threads wake immediately
        self._shutdown_event = threading.Event()

        # Task context for resume
        self.ctx_path = (
            Path.home() / ".hatchery-agents" / self.cfg.agent_id / "task_context.json"
        )
        ensure_dir(self.ctx_path.parent)

        # Message inbox + response tracking
        self._message_inbox: dict[str, dict] = {}      # message_id → event
        self._message_responses: dict[str, dict] = {}   # sent_msg_id → response event
        self._team_updates: list[dict] = []             # broadcasts from other agents

    # ---- Override these in subclass ----

    def create_brain(self):
        """Override to create the LLM brain. Called by __init__."""
        raise NotImplementedError("Subclass must implement create_brain()")

    # ---- Lifecycle ----

    def register(self) -> str:
        """
        Configure webhook with Hatchery platform.

        If the webhook URL is not publicly reachable (e.g. localhost),
        registration will fail and the agent falls back to polling-only mode.
        This is expected for local development — the poll loop still works.
        """
        webhook_url = getattr(self.cfg, "webhook_url", "") or ""
        is_local_url = (
            "localhost" in webhook_url
            or "127.0.0.1" in webhook_url
            or webhook_url.startswith("http://")
        )
        self.poll_only_mode = False

        if not webhook_url:
            logger.info(
                f"[{self.cfg.agent_id}] No webhook_url configured — polling-only mode"
            )
            self.poll_only_mode = True
            self.agent_api_key = ""
            return self.agent_api_key

        logger.info(f"Configuring webhook for {self.cfg.agent_id}: {webhook_url}")
        try:
            resp = self.hatchery.register(self.cfg)
            webhook = resp.get("webhook", {})
            self.agent_api_key = webhook.get("secret", "")
            logger.info(f"Webhook configured: {webhook.get('url', '?')}")
        except Exception as e:
            err_msg = str(e)
            if is_local_url and ("HTTPS" in err_msg or "400" in err_msg):
                logger.info(
                    f"[{self.cfg.agent_id}] Webhook URL is local/HTTP — "
                    f"falling back to polling-only mode"
                )
            else:
                logger.warning(f"Webhook config failed (using polling mode): {e}")
            self.poll_only_mode = True
            self.agent_api_key = ""

        # Register capabilities with Hatchery
        if self.capabilities:
            try:
                self.hatchery._request("PATCH", "agent/capabilities", {
                    "capabilities": self.capabilities,
                })
                logger.info(f"[{self.cfg.agent_id}] Capabilities: {self.capabilities}")
            except Exception as e:
                logger.debug(f"Capability registration failed (non-fatal): {e}")

        return self.agent_api_key

    def run(self):
        """Main entry point: register, start webhook, run heartbeat + poll loop."""
        logger.info(f"Starting agent: {self.cfg.agent_id} "
                    f"[{self.cfg.llm_model}] "
                    f"[{self.cfg.llm_provider}]")
        self.register()
        self.running = True

        # Register signal handlers
        signal.signal(signal.SIGINT, lambda *a: self._shutdown("SIGINT"))
        signal.signal(signal.SIGTERM, lambda *a: self._shutdown("SIGTERM"))

        # Webhook receiver — only start if we successfully registered a webhook
        if not self.poll_only_mode:
            self.webhook = WebhookReceiver(
                port=self.cfg.agent_port,
                agent_api_key=self.agent_api_key,
                event_handlers={
                    "task.assigned": self._on_task_assigned,
                    "message.received": self._on_message_received,
                    "message.response": self._on_message_response,
                    "broadcast": self._on_broadcast,
                    "task.updated": self._on_task_updated,
                    "task.transferred": self._on_task_transferred,
                },
            )
            try:
                self.webhook.start()
                logger.info(f"Webhook server listening on port {self.cfg.agent_port}")
            except Exception as e:
                logger.warning(f"Webhook server failed to start: {e}")
                self.webhook = None
        else:
            logger.info(f"[{self.cfg.agent_id}] Poll-only mode (no webhook receiver)")

        # Heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat"
        )
        self._heartbeat_thread.start()

        # Main work loop
        self._poll_loop()

    def _shutdown(self, sig: str):
        logger.info(f"Received {sig}, shutting down gracefully...")
        self.running = False
        self._shutdown_event.set()  # Wake any sleeping threads immediately
        if self.current_task_id:
            try:
                self.hatchery.update_task_status(
                    self.current_task_id, "blocked",
                    comment=f"Agent shutting down ({sig})"
                )
            except Exception:
                pass

    # ---- Heartbeat ----

    def _heartbeat_loop(self):
        """
        Send heartbeat to Hatchery periodically. Resilient to:
        - 429 rate limits (silent after first warning; the daily iteration
          limit resets on a clock boundary, not per call).
        - Transient network errors (exponential backoff up to 5 min).
        - Repeated failures (never crash; just keep trying).
        """
        interval = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))
        consecutive_failures = 0
        rate_limited_logged = False

        while self.running:
            # Interruptible sleep — returns True if shutdown was signaled
            if self._shutdown_event.wait(timeout=interval):
                break
            if not self.running:
                break
            try:
                self.hatchery.heartbeat(
                    self.cfg.agent_id,
                    status="alive",
                    current_task_id=self.current_task_id,
                    progress_pct=self._get_progress(),
                )
                # Success — reset failure counters
                consecutive_failures = 0
                rate_limited_logged = False
            except Exception as e:
                err_msg = str(e)
                is_session_limit = "Session iteration limit" in err_msg or (
                    "iteration_limit_exceeded" in err_msg and "session" in err_msg.lower()
                )
                is_daily_limit = "Daily iteration limit" in err_msg
                is_rate_limit = (
                    is_session_limit or is_daily_limit or "429" in err_msg
                )
                if is_session_limit:
                    # Session limit is resettable — call GET /context to reset
                    try:
                        self.hatchery.reset_session()
                        if not rate_limited_logged:
                            logger.info(
                                "Heartbeat: session limit hit, session reset via GET /context"
                            )
                            rate_limited_logged = True
                    except Exception:
                        pass
                elif is_rate_limit:
                    if not rate_limited_logged:
                        logger.info(
                            "Heartbeat rate-limited (daily cap). "
                            "Continuing to poll; will stop logging this."
                        )
                        rate_limited_logged = True
                else:
                    consecutive_failures += 1
                    # Exponential backoff for real errors
                    backoff = min(interval * (2 ** consecutive_failures), 300)
                    if consecutive_failures <= 3:
                        logger.warning(f"Heartbeat failed ({consecutive_failures}): {e}")
                    if self._shutdown_event.wait(timeout=backoff):
                        break

    def _get_progress(self) -> Optional[int]:
        """Read progress from task context file."""
        if self.ctx_path.exists():
            try:
                return read_json(self.ctx_path).get("progress_pct")
            except Exception:
                pass
        return None

    # ---- Webhook Handlers ----

    def _on_task_assigned(self, event: dict) -> dict:
        """
        Handle task.assigned webhook from Hatchery.
        Called by WebhookReceiver when Hatchery POSTs to /webhook.
        """
        task_id = event.get("task_id", "")
        title = event.get("title", "")
        project = event.get("project", {})
        logger.info(f"[WEBHOOK] Task assigned: {title} [{task_id}]")

        save_task_context(self.cfg.agent_id, task_id, "webhook_received", {
            "title": title,
            "project": project,
        })

        return {
            "acknowledged": True,
            "action": "starting_task",
            "task_id": task_id,
        }

    def _on_message_received(self, event: dict) -> dict:
        """
        Handle message.received webhook — another agent sent us a message.

        Stores the message in the inbox and auto-replies with an ack.
        Subclasses can override _handle_incoming_message() for custom behavior.
        """
        from_agent = event.get("from_agent_id", "?")
        from_name = event.get("from_agent_name", from_agent)
        content = event.get("content", "")
        message_id = event.get("message_id", "")
        channel = event.get("channel", "direct")
        in_reply_to = event.get("in_reply_to")

        logger.info(f"[MSG] From {from_name}: {content[:120]}")

        # Store in inbox
        self._message_inbox[message_id] = {
            "message_id": message_id,
            "from_agent_id": from_agent,
            "from_agent_name": from_name,
            "content": content,
            "channel": channel,
            "in_reply_to": in_reply_to,
            "received_at": time.time(),
            "processed": False,
        }

        # Let subclass handle it (default: ack)
        response = self._handle_incoming_message(
            from_agent_id=from_agent,
            from_name=from_name,
            content=content,
            message_id=message_id,
            channel=channel,
        )

        # If handler returned a response string, send it back
        if response and message_id:
            try:
                self.hatchery.reply_to_message(message_id, response)
            except Exception as e:
                logger.warning(f"Failed to reply: {e}")

        return {"acknowledged": True, "auto_replied": bool(response)}

    def _handle_incoming_message(self, from_agent_id: str, from_name: str,
                                  content: str, message_id: str,
                                  channel: str) -> str | None:
        """
        Handle messages from other agents.
        - Broadcasts: store as team context (no reply needed)
        - Direct messages: acknowledge
        """
        if channel == "broadcast":
            # Store broadcast as team context — useful for knowing what's done
            self._team_updates.append({
                "from": from_name,
                "content": content,
                "time": time.time(),
            })
            # Keep only last 20 broadcasts
            self._team_updates = self._team_updates[-20:]
            logger.info(f"[{self.cfg.agent_id}] Team update from {from_name}: {content[:80]}")
            return None
        return f"[{self.cfg.agent_id}] Got it — will look into it."

    def _on_message_response(self, event: dict) -> dict:
        """
        Handle message.response webhook — someone replied to our message.
        """
        in_reply_to = event.get("in_reply_to", "")
        from_agent = event.get("from_agent_name", event.get("from_agent_id", "?"))
        content = event.get("content", "")

        logger.info(f"[RESPONSE] {from_agent} replied to {in_reply_to}: {content[:120]}")

        # Store in responses map
        if in_reply_to:
            self._message_responses[in_reply_to] = {
                "from_agent": from_agent,
                "content": content,
                "received_at": time.time(),
            }

        # Let subclass handle it
        self._handle_message_response(in_reply_to, from_agent, content)
        return {"acknowledged": True}

    def _handle_message_response(self, in_reply_to: str, from_agent: str,
                                  content: str) -> None:
        """Override in subclasses for custom response handling."""
        pass

    def _on_broadcast(self, event: dict) -> dict:
        """Handle broadcast webhook."""
        from_agent = event.get("from_agent_id", "?")
        content = event.get("content", "")
        logger.info(f"[BROADCAST] from {from_agent}: {content[:100]}")
        return {"acknowledged": True}

    def _on_task_updated(self, event: dict) -> dict:
        """Handle task.updated webhook."""
        task_id = event.get("task_id", "")
        logger.info(f"[WEBHOOK] Task updated: {task_id}")
        return {"acknowledged": True}

    def _on_task_transferred(self, event: dict) -> dict:
        """Handle task.transferred webhook — another agent handed off a task."""
        task_id = event.get("task_id", "")
        from_agent = event.get("from_agent_id", "?")
        logger.info(f"[WEBHOOK] Task transferred from {from_agent}: {task_id}")
        return {"acknowledged": True}

    # ---- Poll Loop ----

    def _poll_loop(self):
        """
        Main work loop. Polls Hatchery for notifications and available tasks.

        Resilient to:
        - 429 rate limits (silent after first warning)
        - Transient network errors (exponential backoff up to 5 min)
        - Never crashes on any single iteration
        """
        interval = int(os.environ.get("POLL_INTERVAL", "30"))
        consecutive_failures = 0
        rate_limited_logged = False
        idle_logged = False

        logger.info(f"[{self.cfg.agent_id}] Poll loop started (every {interval}s)")

        while self.running:
            try:
                # Step 1: Poll notifications (messages from other agents, etc.)
                try:
                    self._poll_notifications()
                except Exception as e:
                    logger.debug(f"Notification poll failed: {e}")

                # Step 2: Poll for available tasks
                tasks = self.hatchery.get_available_tasks()

                if tasks:
                    # Reset idle state
                    idle_logged = False
                    selected = self._select_task(tasks)
                    if selected:
                        logger.info(
                            f"[{self.cfg.agent_id}] Picked up task: "
                            f"{selected.get('title', '?')} "
                            f"({selected.get('id', '?')[:8]})"
                        )
                        self._execute_task(selected)
                else:
                    if not idle_logged:
                        logger.info(f"[{self.cfg.agent_id}] Idle — no tasks available")
                        idle_logged = True

                # Success — reset failure counters
                consecutive_failures = 0
                rate_limited_logged = False

            except Exception as e:
                err_msg = str(e)
                is_session_limit = "Session iteration limit" in err_msg
                is_rate_limit = (
                    is_session_limit
                    or "iteration_limit_exceeded" in err_msg
                    or "429" in err_msg
                )
                if is_session_limit:
                    # Reset the session counter via GET /context
                    try:
                        self.hatchery.reset_session()
                        if not rate_limited_logged:
                            logger.info(
                                "Poll: session limit hit, session reset via GET /context"
                            )
                            rate_limited_logged = True
                    except Exception:
                        pass
                elif is_rate_limit:
                    if not rate_limited_logged:
                        logger.info(
                            "Poll rate-limited (daily cap). Continuing at normal interval."
                        )
                        rate_limited_logged = True
                else:
                    consecutive_failures += 1
                    if consecutive_failures <= 3:
                        logger.warning(
                            f"Poll loop error ({consecutive_failures}): {e}"
                        )
                    # Exponential backoff on repeated non-rate-limit failures
                    backoff = min(interval * (2 ** (consecutive_failures - 1)), 300)
                    if self._shutdown_event.wait(timeout=backoff):
                        break
                    continue

            # Interruptible sleep between polls
            if self._shutdown_event.wait(timeout=interval):
                break

    def _select_task(self, tasks: list) -> Optional[dict]:
        """
        Select which task to pick up from the available queue.
        Prefers the configured workspace, falls back to first available.
        Returns None if no task matches.
        """
        if not tasks:
            return None

        target_ws = os.environ.get("WANNAFUN_WS", "") or os.environ.get("HATCHERY_WS", "")
        if target_ws:
            for task in tasks:
                hp = task.get("hatchery_projects", {})
                ws = hp.get("workspace_id", "")
                if ws == target_ws:
                    return task

        # No workspace match — take the first available
        return tasks[0]

    def _poll_notifications(self):
        """
        Poll for pending notifications and process them.
        Handles: message.received, task.assigned, conflict.raised, ack.required,
        and other webhook events from the Hatchery platform or other agents.
        """
        try:
            notifications = self.hatchery.get_notifications()
            if not notifications:
                return

            logger.info(f"[{self.cfg.agent_id}] {len(notifications)} notification(s) pending")

            for notif in notifications:
                self._process_notification(notif)
        except Exception as e:
            logger.warning(f"Notification poll failed: {e}")

    def _process_notification(self, notif: dict):
        """
        Process a single notification (webhook delivery).

        Handles different event types:
          - message.received: respond to the sender via brain
          - task.assigned: claim and execute the task
          - conflict.raised: log conflict and acknowledge
          - ack.required: respond with acknowledgment
          - human.responded: log the human response
        """
        delivery_id = notif.get("id", "")
        payload = notif.get("payload", {})
        event_type = payload.get("event", notif.get("event_type", ""))
        data = payload.get("data", {})

        logger.info(f"[{self.cfg.agent_id}] Processing: {event_type}")

        try:
            if event_type == "message.received":
                self._on_message_received_webhook(data, delivery_id)
            elif event_type == "task.assigned":
                self._on_task_assigned_webhook(data, delivery_id)
            elif event_type == "conflict.raised":
                self._on_conflict_raised_webhook(data, delivery_id)
            elif event_type == "ack.required":
                self._on_ack_required_webhook(data, delivery_id)
            elif event_type == "human.responded":
                self._on_human_responded_webhook(data, delivery_id)
            else:
                logger.debug(f"[{self.cfg.agent_id}] Unhandled event type: {event_type}")
                # Still acknowledge so it doesn't keep appearing
                self.hatchery.acknowledge_notification(delivery_id, status="acknowledged")
        except Exception as e:
            logger.error(f"[{self.cfg.agent_id}] Notification processing error: {e}")
            # Acknowledge with error status so it doesn't block
            try:
                self.hatchery.acknowledge_notification(
                    delivery_id,
                    response=f"Processing error: {e}",
                    status="acknowledged"
                )
            except Exception:
                pass

    def _on_message_received_webhook(self, data: dict, delivery_id: str):
        """Handle message.received — generate and send a response."""
        message_id = data.get("message_id", "")
        from_agent_id = data.get("from_agent_id", "?")
        content = data.get("content", "")

        logger.info(f"[{self.cfg.agent_id}] Message from {from_agent_id}: {content[:80]}")

        # Generate response using brain
        response_text = ""
        try:
            prompt = (
                f"You received a message from another agent ({from_agent_id}):\n\n"
                f"{content}\n\n"
                f"Generate a helpful, concise response. Be collaborative and practical."
            )
            response_text = self.brain.complete(prompt)
            response_text = response_text.strip()
        except Exception as e:
            response_text = f"Acknowledged. I'll look into this. (error: {e})"

        # Send response back via platform
        if message_id:
            try:
                self.hatchery.reply_to_message(message_id, response_text)
                logger.info(f"[{self.cfg.agent_id}] Response sent to {from_agent_id}")
            except Exception as e:
                logger.error(f"[{self.cfg.agent_id}] Failed to send response: {e}")

        # Acknowledge the notification
        self.hatchery.acknowledge_notification(delivery_id, response=response_text, status="responded")

    def _on_task_assigned_webhook(self, data: dict, delivery_id: str):
        """Handle task.assigned — claim and execute the task."""
        task_id = data.get("id", "") or data.get("task_id", "")
        title = data.get("title", "Assigned task")
        logger.info(f"[{self.cfg.agent_id}] Task assigned: {title} ({task_id})")

        # Claim and execute
        try:
            self.hatchery.claim_task(task_id)
            # Get full task data for execution
            tasks = [t for t in self.hatchery.get_available_tasks() if t.get("id") == task_id]
            if tasks:
                self._execute_task(tasks[0])
            else:
                # Task was already claimed — acknowledge
                self.hatchery.acknowledge_notification(delivery_id, status="acknowledged")
        except Exception as e:
            logger.warning(f"[{self.cfg.agent_id}] Task claim failed: {e}")
            self.hatchery.acknowledge_notification(
                delivery_id,
                response=f"Could not claim: {e}",
                status="acknowledged"
            )

    def _on_conflict_raised_webhook(self, data: dict, delivery_id: str):
        """Handle conflict.raised — log and acknowledge."""
        title = data.get("title", "Conflict")
        severity = data.get("severity", "warning")
        description = data.get("description", "")
        logger.warning(f"[{self.cfg.agent_id}] CONFLICT [{severity}]: {title} — {description}")
        self.hatchery.acknowledge_notification(delivery_id, status="acknowledged")

    def _on_ack_required_webhook(self, data: dict, delivery_id: str):
        """Handle ack.required — send acknowledgment."""
        message_id = data.get("message_id", "")
        content = data.get("content", "Acknowledged")
        if message_id:
            try:
                self.hatchery.reply_to_message(message_id, str(content))
            except Exception as e:
                logger.error(f"[{self.cfg.agent_id}] Ack failed: {e}")
        self.hatchery.acknowledge_notification(delivery_id, status="acknowledged")

    def _on_human_responded_webhook(self, data: dict, delivery_id: str):
        """Handle human.responded — log and acknowledge."""
        content = data.get("content", "")
        logger.info(f"[{self.cfg.agent_id}] Human response: {content[:100]}")
        self.hatchery.acknowledge_notification(delivery_id, status="acknowledged")

    # ---- Task Execution ----

    def _execute_task(self, task: dict):
        """
        Full task execution pipeline with two paths:

        Agentic path (Claude Code in agent mode):
          1. Claim → 2. Clone → 3. Let agent run (reads, writes, builds) → 4. Commit/push → 5. PR

        Single-shot path (MiniMax, Ollama, Gemini, OpenAI):
          1. Claim → 2. Clone → 3. Build prompt with file context → 4. LLM generates code
          → 5. Parse + write → 6. Build check → 7. If fail, retry with errors → 8. Commit/push → 9. PR
        """
        task_id = task.get("id")
        title = task.get("title", "")
        description = task.get("description", "")
        project = task.get("hatchery_projects", {})

        logger.info(f"[{self.cfg.agent_id}] Executing task: {title}")
        self.current_task_id = task_id

        save_task_context(self.cfg.agent_id, task_id, "executing", {
            "title": title, "project": project.get("name")
        })

        is_agentic = getattr(self.brain, 'is_agentic', False)

        # Determine if this is a scaffold task (push to main) vs feature (branch + PR)
        is_scaffold = "[1/6]" in title or "[1/1]" in title

        try:
            # Step 1: Claim
            self._claim_task(task_id)
            self._update_progress(task_id, "in_progress", 10)

            # Step 2: Get repo URL — use existing or create new
            repo_url = project.get("repo_url", "")
            if is_scaffold:
                branch_name = "main"
            else:
                branch_name = self._make_branch_name(task_id, title)
            repo_dir = self._setup_repo(repo_url, branch_name, project)
            self._update_progress(task_id, "in_progress", 20)

            if is_agentic:
                self._execute_agentic(task, repo_dir, repo_url, branch_name)
            else:
                self._execute_single_shot(task, repo_dir, repo_url, branch_name)

            # Broadcast completion to other agents
            self._broadcast_completion(task, project)

            clear_task_context(self.cfg.agent_id)
            logger.info(f"[{self.cfg.agent_id}] Task DONE: {title}")

        except Exception as e:
            logger.error(f"Task FAILED [{task_id}]: {e}")
            try:
                # Only reset to ready if the task isn't already done
                # (another agent may have completed it while we were working)
                task_check = self.hatchery._request("GET", f"agent/tasks/{task_id}")
                current_status = task_check.get("task", {}).get("status", "")
                if current_status not in ("done", "review"):
                    self.hatchery.update_task_status(
                        task_id, "ready", comment=f"{self.cfg.agent_id} error: {e}"
                    )
                else:
                    logger.info(f"[{self.cfg.agent_id}] Task {task_id[:8]} already {current_status} — not resetting")
            except Exception:
                pass

        finally:
            self.current_task_id = None

    def _execute_agentic(self, task: dict, repo_dir: Optional[Path],
                         repo_url: str, branch_name: str):
        """
        Agentic execution: Claude Code runs as a full agent in the repo.
        It reads files, writes code, runs commands, and iterates on errors.
        We just need to commit/push/PR the result.
        """
        task_id = task.get("id")
        title = task.get("title", "")
        description = task.get("description", "")
        project = task.get("hatchery_projects", {})

        # Set the working directory for the agentic brain
        if repo_dir and hasattr(self.brain, 'set_cwd'):
            self.brain.set_cwd(str(repo_dir))

        # Build prompt (agentic version — no file contents needed)
        prompt = self._build_prompt(title, description, repo_url, repo_dir, task)
        self._update_progress(task_id, "in_progress", 30)

        # Let the agent run — it handles everything
        logger.info(f"[{self.cfg.agent_id}] Running agentic brain in {repo_dir}...")
        response = self.brain.complete(prompt, system=self.system_prompt)
        self._update_progress(task_id, "in_progress", 80)
        logger.info(f"[{self.cfg.agent_id}] Agent output: {response[:500]}")

        # Commit whatever the agent produced
        commit_msg = self._make_commit_msg(title, task_id)
        pushed = False
        if repo_dir:
            self._commit_and_push(commit_msg, task_id)
            pushed = True

        # Deploy + PR
        deploy_url = self._try_deploy(project, repo_dir, pushed)
        if pushed and repo_url:
            self._try_open_pr(branch_name, title, task_id, deploy_url)

        # Mark done
        note = f"Completed by {self.cfg.agent_id} ({self.cfg.llm_model}) [agentic]"
        if deploy_url:
            note += f" | Deployed: {deploy_url}"
        self.hatchery.update_task_status(task_id, "done", comment=note)

    def _execute_single_shot(self, task: dict, repo_dir: Optional[Path],
                             repo_url: str, branch_name: str):
        """
        Single-shot execution with retry: call LLM, parse output, write files,
        verify build, and retry with error feedback if build fails.
        """
        task_id = task.get("id")
        title = task.get("title", "")
        description = task.get("description", "")
        project = task.get("hatchery_projects", {})

        max_attempts = 3
        build_errors = ""

        for attempt in range(1, max_attempts + 1):
            logger.info(f"[{self.cfg.agent_id}] Attempt {attempt}/{max_attempts}")

            # Build prompt — include build errors from previous attempt
            prompt = self._build_prompt(title, description, repo_url, repo_dir, task)
            if build_errors:
                prompt += f"""

## PREVIOUS ATTEMPT FAILED
The code you wrote in the previous attempt had build errors. Fix them.

Build command output:
```
{build_errors}
```

Fix the errors above and output the corrected files.
"""
            pct = 30 + (attempt - 1) * 15
            self._update_progress(task_id, "in_progress", min(pct, 70))

            # Call the LLM
            logger.info(f"[{self.cfg.agent_id}] Calling brain ({self.cfg.llm_model})...")
            response = self.brain.complete(prompt, system=self.system_prompt)

            if not response or not response.strip():
                logger.warning(f"[{self.cfg.agent_id}] Empty response from brain")
                build_errors = "LLM returned empty response. You must output code."
                continue

            # Parse + write files
            files_written = 0
            if repo_dir:
                writes = CodeParser.parse(response, repo_dir)
                if writes:
                    CodeParser.apply_writes(writes)
                    files_written = len(writes)
                    logger.info(f"Wrote {files_written} files")
                else:
                    logger.warning(f"[{self.cfg.agent_id}] No files parsed from response")
                    # Log first 500 chars to help debug
                    logger.debug(f"Response preview: {response[:500]}")
                    build_errors = (
                        "No files were parsed from your response. You MUST output a JSON manifest "
                        "wrapped in ```json ... ``` with a 'files' array. Each entry needs 'path' "
                        "and 'content' keys. Do not include explanatory text."
                    )
                    continue

            # Verify build
            if repo_dir and files_written > 0:
                build_result = self._run_build(repo_dir)
                if build_result["ok"]:
                    logger.info(f"[{self.cfg.agent_id}] Build passed on attempt {attempt}")
                    build_errors = ""
                    break
                else:
                    build_errors = build_result["output"]
                    logger.warning(f"[{self.cfg.agent_id}] Build failed, will retry: "
                                   f"{build_errors[:200]}")
                    continue
            else:
                # No build command or no files — accept the result
                break

        self._update_progress(task_id, "in_progress", 80)

        # Commit + push
        commit_msg = self._make_commit_msg(title, task_id)
        pushed = False
        if repo_dir:
            self._commit_and_push(commit_msg, task_id)
            pushed = True

        # Deploy + PR
        deploy_url = self._try_deploy(project, repo_dir, pushed)
        if pushed and repo_url:
            self._try_open_pr(branch_name, title, task_id, deploy_url)

        # Determine final status based on whether code was actually produced and builds
        files_on_disk = bool(repo_dir and any(repo_dir.iterdir()))
        if build_errors and files_written == 0:
            # No code produced at all — mark as ready so another agent can try
            status = "ready"
            note = (f"{self.cfg.agent_id} could not produce parseable code after "
                    f"{max_attempts} attempts. Releasing for another agent.")
            self.hatchery.update_task_status(task_id, status, comment=note)
            return
        elif build_errors:
            # Code produced but build failed — mark as review for inspection
            status = "review"
            note = (f"{self.cfg.agent_id} ({self.cfg.llm_model}) wrote code but "
                    f"build failed. Needs review or another agent to fix.")
        else:
            status = "done"
            note = f"Completed by {self.cfg.agent_id} ({self.cfg.llm_model})"

        if deploy_url:
            note += f" | Deployed: {deploy_url}"
        self.hatchery.update_task_status(task_id, status, comment=note)

    # ---- Deploy + PR Helpers ----

    def _try_deploy(self, project: dict, repo_dir: Optional[Path],
                    pushed: bool) -> str:
        """Attempt Vercel deployment. Returns deploy URL or empty string."""
        vercel_project_id = project.get("vercel_project_id")
        if not vercel_project_id or not pushed:
            return ""
        try:
            deploy_result = self.deploy.deploy(repo_dir, vercel_project_id)
            deploy_url = deploy_result.get("url", "")
            if deploy_url and self.deploy.smoke_test(deploy_url):
                logger.info(f"Deploy OK: {deploy_url}")
            else:
                logger.warning(f"Deploy may have failed: {deploy_result}")
            return deploy_url
        except Exception as e:
            logger.warning(f"Deploy error (non-fatal): {e}")
            return ""

    def _try_open_pr(self, branch_name: str, title: str,
                     task_id: str, deploy_url: str):
        """Attempt to open a PR. Non-fatal on failure. Skip for main branch."""
        if branch_name == "main":
            logger.info("Pushed to main — no PR needed")
            return
        try:
            pr_result = self._open_pr(branch_name, title, task_id, deploy_url)
            logger.info(f"PR: {pr_result.get('url', 'no url')}")
        except Exception as e:
            logger.warning(f"PR error (non-fatal): {e}")

    def _broadcast_completion(self, task: dict, project: dict):
        """Broadcast a status message to other agents after completing a task."""
        try:
            task_title = task.get("title", "?")
            project_name = project.get("name", "?")
            repo_url = project.get("repo_url", "")

            # Build a useful message for other agents
            content = (
                f"Finished: {task_title} on {project_name}. "
                f"Repo: {repo_url}. "
                f"Agent: {self.cfg.agent_id}."
            )
            self.hatchery.broadcast(content, message_type="status_update")
            logger.info(f"[{self.cfg.agent_id}] Broadcast: {content[:80]}")
        except Exception as e:
            logger.debug(f"Broadcast failed (non-fatal): {e}")

    # ---- Git Helpers ----

    def _setup_repo(self, repo_url: str, branch_name: str, project: dict) -> Optional[Path]:
        """
        Clone or create the repo and create a feature branch.
        If repo_url is empty or repo doesn't exist, creates it on GitHub.
        """
        import re
        project_name = project.get("name", "project")

        if not repo_url:
            logger.warning("No repo_url in project — will scaffold a new one")
            # Create a local scaffold dir for this project
            slug = re.sub(r'[^a-zA-Z0-9_-]', '-', project_name.lower())
            repo_dir = Path.home() / "hatchery-repos" / slug
            repo_dir.mkdir(parents=True, exist_ok=True)
            # Try to init and push if we have code, otherwise leave empty dir
            self._repo_dir = repo_dir
            return repo_dir

        # Extract owner/repo from URL
        parts = repo_url.rstrip("/").replace(".git", "").split("/")
        owner = parts[-2] if len(parts) >= 2 else "wannanaplabs"
        repo_name = parts[-1] if len(parts) >= 1 else project_name.lower().replace(" ", "-")

        try:
            repo_dir = self.git.clone_or_pull(repo_url)
            if branch_name != "main":
                self.git.new_branch(branch_name)
            return repo_dir
        except Exception as e:
            logger.warning(f"Clone failed ({e}) — creating GitHub repo and scaffolding locally")
            # Repo doesn't exist on GitHub yet — create it and scaffold locally
            slug = repo_name
            repo_dir = Path.home() / "hatchery-repos" / slug
            repo_dir.mkdir(parents=True, exist_ok=True)

            # Init git locally with a placeholder commit
            subprocess.run(["git", "init"], cwd=repo_dir, check=False)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", f"Initial scaffold for {project_name}"],
                cwd=repo_dir, check=False
            )

            # Create GitHub repo and push
            result = self.git.init_and_push(
                repo_dir, owner, slug,
                description=f"{project_name} — built by Hatchery agents",
                branch=branch_name, private=True
            )
            if result:
                logger.info(f"Created and pushed repo: {owner}/{slug}")
                return repo_dir
            else:
                logger.warning(f"Could not create GitHub repo — working in local dir only")
                self._repo_dir = repo_dir
                return repo_dir

    def _commit_and_push(self, commit_msg: str, task_id: str):
        """Stage all changes, commit, and push to remote."""
        r = self.git.add_commit(commit_msg)
        if r.returncode == 0:
            self.git.push()
            logger.info(f"Committed and pushed: {commit_msg[:60]}")
        else:
            logger.info("Nothing to commit (no changes detected)")

    def _open_pr(self, branch_name: str, title: str,
                 task_id: str, deploy_url: str = "") -> dict:
        """Open a GitHub PR via gh CLI."""
        body = (
            f"## Hatchery Task\n"
            f"**Task ID:** `{task_id}`\n"
            f"**Agent:** {self.cfg.agent_id}\n"
        )
        if deploy_url:
            body += f"\n**Deploy:** {deploy_url}"
        return self.git.open_pr(
            title=f"[Hatchery] {title}",
            body=body,
            head_branch=branch_name,
        )

    # ---- Context Reading ----

    def _read_key_files(self, repo_dir: Path) -> str:
        """
        Read key files from the repo to give the LLM real context.
        Returns a formatted string of file contents.
        """
        key_files = [
            "README.md", "readme.md",
            "package.json",
            "tsconfig.json",
            "next.config.ts", "next.config.js", "next.config.mjs",
            "vite.config.ts", "vite.config.js",
            "pyproject.toml", "requirements.txt",
            "Cargo.toml",
            ".env.example", ".env.local.example",
            "src/app/layout.tsx", "src/app/page.tsx",
            "app/layout.tsx", "app/page.tsx",
            "src/index.ts", "src/index.tsx", "src/main.ts", "src/main.tsx",
            "src/App.tsx", "src/App.vue",
        ]
        sections = []
        total_chars = 0
        max_chars = 15000  # Cap total context to ~15k chars

        for fname in key_files:
            fpath = repo_dir / fname
            if fpath.exists() and fpath.is_file():
                try:
                    content = fpath.read_text(errors="replace")
                    # Cap individual files at 3000 chars
                    if len(content) > 3000:
                        content = content[:3000] + "\n... (truncated)"
                    if total_chars + len(content) > max_chars:
                        break
                    sections.append(f"### {fname}\n```\n{content}\n```")
                    total_chars += len(content)
                except Exception:
                    pass

        return "\n\n".join(sections) if sections else ""

    def _get_repo_tree(self, repo_dir: Path) -> str:
        """Build a directory tree string for the repo."""
        if not repo_dir or not repo_dir.exists():
            return ""
        try:
            tree_lines = []
            for root, dirs, files in os.walk(repo_dir):
                dirs[:] = [d for d in dirs if d not in (
                    ".git", "node_modules", "__pycache__", ".next", ".nuxt",
                    "dist", "build", ".venv", "venv", ".cache", ".turbo",
                )]
                for f in sorted(files)[:20]:
                    rel = Path(root).relative_to(repo_dir)
                    tree_lines.append(f"  {rel}/{f}" if str(rel) != "." else f"  {f}")
            return "\n".join(tree_lines[:150])
        except Exception as e:
            logger.warning(f"Could not build repo tree: {e}")
            return ""

    # ---- Build Verification ----

    def _detect_build_command(self, repo_dir: Path) -> Optional[str]:
        """Detect the build/check command for this repo."""
        pkg_json = repo_dir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                scripts = pkg.get("scripts", {})
                # Check if node_modules exists — if not, must install first
                needs_install = not (repo_dir / "node_modules").exists()
                install_prefix = "npm install && " if needs_install else ""
                # Prefer build, then typecheck, then lint
                if "build" in scripts:
                    return f"{install_prefix}npm run build"
                if "typecheck" in scripts:
                    return f"{install_prefix}npm run typecheck"
                if "lint" in scripts:
                    return f"{install_prefix}npm run lint"
                # If there's a package.json but no build script, just install
                if needs_install:
                    return "npm install"
                return None
            except Exception:
                pass

        if (repo_dir / "pyproject.toml").exists():
            return "python -m py_compile $(find . -name '*.py' -not -path './.venv/*')"

        if (repo_dir / "Cargo.toml").exists():
            return "cargo check"

        return None

    def _run_build(self, repo_dir: Path, command: Optional[str] = None) -> dict:
        """
        Run a build/verification command in the repo directory.
        Returns {"ok": bool, "output": str, "command": str}.
        """
        cmd = command or self._detect_build_command(repo_dir)
        if not cmd:
            return {"ok": True, "output": "No build command detected", "command": ""}

        logger.info(f"Running build: {cmd}")
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=repo_dir,
                capture_output=True, timeout=120,
            )
            stdout = proc.stdout.decode(errors="replace")
            stderr = proc.stderr.decode(errors="replace")
            output = (stdout + "\n" + stderr).strip()
            # Cap output to avoid blowing up the prompt
            if len(output) > 5000:
                output = output[-5000:]

            ok = proc.returncode == 0
            if ok:
                logger.info(f"Build passed: {cmd}")
            else:
                logger.warning(f"Build failed (rc={proc.returncode}): {output[:300]}")
            return {"ok": ok, "output": output, "command": cmd}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "Build timed out after 120s", "command": cmd}
        except Exception as e:
            return {"ok": False, "output": str(e), "command": cmd}

    # ---- Prompt Building ----

    def _build_prompt(self, title: str, description: str,
                      repo_url: str, repo_dir: Optional[Path],
                      task: dict) -> str:
        """
        Build the task prompt sent to the LLM brain.
        Includes repo structure, file contents, and output format instructions.
        """
        repo_tree = self._get_repo_tree(repo_dir) if repo_dir else ""
        file_contents = self._read_key_files(repo_dir) if repo_dir else ""

        project = task.get("hatchery_projects", {})
        stack = project.get("stack", {})
        stack_str = ""
        if stack:
            stack_str = "\n".join(f"  - {k}: {v}" for k, v in stack.items())

        # Check if brain is agentic (e.g. Claude Code in agent mode)
        is_agentic = getattr(self.brain, 'is_agentic', False)

        # Pre-format sections to avoid backslashes in f-string expressions
        stack_section = "Tech stack:\n" + stack_str if stack_str else ""
        tree_section = "Directory structure:\n" + repo_tree if repo_tree else "(Empty repository)"
        files_section = "## EXISTING FILES\n\n" + file_contents if file_contents else ""

        if is_agentic:
            # Agentic prompt — the agent can read/write/execute directly
            return f"""Complete the following development task.

## TASK
Title: {title}
Description: {description}

## REPOSITORY
URL: {repo_url}
Working directory: {repo_dir}
{stack_section}

## INSTRUCTIONS
1. Explore the repository — read existing files to understand the codebase structure
2. Implement the task — create or modify files as needed
3. Write COMPLETE, WORKING code — not stubs or placeholders
4. If there's a package.json, run `npm install` if you add dependencies
5. Run the build command to verify your code compiles: try `npm run build` or equivalent
6. If the build fails, read the errors and fix them
7. Make sure all files are saved

Focus on producing working code. If the repo is empty, scaffold the full project.
"""
        else:
            # Single-shot prompt — LLM must output structured file content
            return f"""You are an autonomous coding agent. Complete the task below.

## TASK
Title: {title}
Description: {description}

## REPOSITORY
URL: {repo_url}
{stack_section}
{tree_section}

{files_section}

## INSTRUCTIONS
1. Study the existing files above to understand the codebase
2. Implement the task by creating or modifying files
3. Write COMPLETE file contents — not snippets or diffs
4. Include ALL necessary files (package.json, configs, source files)
5. If the repo is empty, scaffold the entire project from scratch

## OUTPUT FORMAT
You MUST output a JSON manifest wrapped in a ```json code fence. This is critical — if you
don't use this format, your code will not be saved.

```json
{{
  "files": [
    {{
      "path": "relative/path/to/file.tsx",
      "content": "full file content here"
    }}
  ]
}}
```

Rules:
- Every file must have "path" (relative to repo root) and "content" (complete file text)
- Include EVERY file that needs to be created or modified
- Do NOT include explanatory text outside the JSON block
- The JSON must be valid — escape special characters in content strings properly
"""

    # ---- Hatchery Helpers ----

    def _claim_task(self, task_id: str):
        try:
            self.hatchery.claim_task(task_id)
            logger.info(f"Claimed task: {task_id}")
        except Exception as e:
            logger.warning(f"Claim may have failed (already claimed?): {e}")

    def _update_progress(self, task_id: str, status: str, pct: int,
                          comment: str = ""):
        try:
            self.hatchery.update_task_status(task_id, status,
                                            comment=comment, progress_pct=pct)
        except Exception as e:
            logger.warning(f"Progress update failed: {e}")

    # ---- Utility ----

    @staticmethod
    def _make_branch_name(task_id: str, title: str) -> str:
        """Generate a sanitized git branch name."""
        # Task ID suffix for uniqueness
        suffix = task_id[:8] if task_id else "task"
        # Sanitize title
        safe = re.sub(r"[^a-zA-Z0-9\s\-]", "", title)
        safe = re.sub(r"\s+", "-", safe).lower()[:40]
        return f"feat/hatchery-{safe}-{suffix}"

    @staticmethod
    def _make_commit_msg(title: str, task_id: str) -> str:
        return f"feat({task_id[:8]}): {title} [Hatchery task]"
