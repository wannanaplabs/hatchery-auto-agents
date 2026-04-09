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
        """
        writes: dict[Path, str] = {}

        # Try JSON manifest first (most reliable)
        manifest_writes = cls._parse_json_manifest(text, repo_dir)
        writes.update(manifest_writes)

        # Try fenced code blocks
        fence_writes = cls._parse_fenced_blocks(text, repo_dir)
        writes.update(fence_writes)

        # Try CREATE: /path directives
        directive_writes = cls._parse_directives(text, repo_dir)
        writes.update(directive_writes)

        return writes

    @classmethod
    def _parse_json_manifest(cls, text: str, repo_dir: Path) -> dict[Path, str]:
        """Parse ```json ... { "files": [...] } ``` blocks."""
        writes: dict[Path, str] = {}
        # Split by ```json ... ``` fences, then parse each as JSON
        pattern = re.compile(r"```json\s*(.+?)\s*```", re.DOTALL)
        for m in pattern.finditer(text):
            json_text = m.group(1).strip()
            try:
                data = json.loads(json_text)
                files = data.get("files", [])
                if isinstance(files, list):
                    for f in files:
                        path = repo_dir / f["path"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        content = f.get("content", "")
                        # Decrypt if encrypted
                        if f.get("encrypted"):
                            content = cls._decrypt(content, os.environ.get("CODE_CIPHER", ""))
                        writes[path] = content
            except (json.JSONDecodeError, KeyError, OSError):
                pass
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
        self.git = GitManager(github_token=self.cfg.github_token)
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

        # Task context for resume
        self.ctx_path = (
            Path.home() / ".hatchery-agents" / self.cfg.agent_id / "task_context.json"
        )
        ensure_dir(self.ctx_path.parent)

        # Message inbox + response tracking
        self._message_inbox: dict[str, dict] = {}      # message_id → event
        self._message_responses: dict[str, dict] = {}   # sent_msg_id → response event

    # ---- Override these in subclass ----

    def create_brain(self):
        """Override to create the LLM brain. Called by __init__."""
        raise NotImplementedError("Subclass must implement create_brain()")

    # ---- Lifecycle ----

    def register(self) -> str:
        """
        Register with Hatchery. Returns the agent_api_key.
        Stores it in self.agent_api_key.
        """
        logger.info(f"Registering {self.cfg.agent_id} with Hatchery...")
        resp = self.hatchery.register(self.cfg)
        self.agent_api_key = resp.get("agent_api_key", "")
        if not self.agent_api_key:
            logger.warning("No agent_api_key in registration response — "
                           "webhook auth may not work")
        logger.info(f"Registered: {self.cfg.agent_id} → {self.agent_api_key[:12]}...")
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

        # Webhook receiver
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
        self.webhook.start()
        logger.info(f"Webhook server listening on port {self.cfg.agent_port}")

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
        """Send heartbeat to Hatchery every 30 seconds."""
        while self.running:
            time.sleep(30)
            if not self.running:
                break
            try:
                self.hatchery.heartbeat(
                    self.cfg.agent_id,
                    status="alive",
                    current_task_id=self.current_task_id,
                    progress_pct=self._get_progress(),
                )
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")

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
        Override in subclasses for custom message handling.
        Return a string to auto-reply, or None to stay silent.
        Default: ack all direct messages, stay silent on broadcasts.
        """
        if channel == "broadcast":
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
        Main work loop. Polls Hatchery for available tasks.
        If a task is available and no webhook-assigned task is in progress,
        claim and execute it.
        """
        while self.running:
            try:
                tasks = self.hatchery.get_available_tasks()
                if tasks:
                    # Prefer wannafun workspace tasks
                    for task in tasks:
                        hp = task.get("hatchery_projects", {})
                        ws = hp.get("workspace_id", "")
                        target_ws = os.environ.get("WANNAFUN_WS", "")
                        if target_ws and ws == target_ws:
                            self._execute_task(task)
                            break
                    else:
                        # No wannafun task, take first available
                        self._execute_task(tasks[0])
                else:
                    logger.debug(f"[{self.cfg.agent_id}] No tasks, sleeping 30s...")
            except Exception as e:
                logger.error(f"Poll loop error: {e}")

            time.sleep(30)

    # ---- Task Execution ----

    def _execute_task(self, task: dict):
        """
        Full task execution pipeline:
          1. Claim
          2. Clone repo
          3. Send to brain
          4. Parse code output + write files
          5. Commit + push
          6. Deploy (optional)
          7. Mark done
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

        try:
            # Step 1: Claim
            self._claim_task(task_id)
            self._update_progress(task_id, "in_progress", 10)

            # Step 2: Clone / pull repo
            github_repo = project.get("github_repo", "")
            branch_name = self._make_branch_name(task_id, title)
            repo_dir = self._setup_repo(github_repo, branch_name)
            self._update_progress(task_id, "in_progress", 20)

            # Step 3: Build prompt
            prompt = self._build_prompt(title, description, github_repo, repo_dir, task)
            self._update_progress(task_id, "in_progress", 30)

            # Step 4: Get brain response
            logger.info(f"[{self.cfg.agent_id}] Calling brain ({self.cfg.llm_model})...")
            response = self.brain.complete(prompt, system=self.system_prompt)
            self._update_progress(task_id, "in_progress", 60)

            # Step 5: Parse + write files
            if repo_dir:
                writes = CodeParser.parse(response, repo_dir)
                if writes:
                    CodeParser.apply_writes(writes)
                    logger.info(f"Wrote {len(writes)} files")

            # Step 6: Commit + push
            commit_msg = self._make_commit_msg(title, task_id)
            pushed = False
            if repo_dir:
                self._commit_and_push(commit_msg, task_id)
                pushed = True

            # Step 7: Deploy (if configured)
            vercel_project_id = project.get("vercel_project_id")
            deploy_url = ""
            if vercel_project_id and pushed:
                try:
                    deploy_result = self.deploy.deploy(repo_dir, vercel_project_id)
                    deploy_url = deploy_result.get("url", "")
                    if deploy_url and self.deploy.smoke_test(deploy_url):
                        logger.info(f"Deploy OK: {deploy_url}")
                    else:
                        logger.warning(f"Deploy may have failed: {deploy_result}")
                except Exception as e:
                    logger.warning(f"Deploy error (non-fatal): {e}")

            # Step 8: Open PR
            if pushed and github_repo:
                try:
                    pr_result = self._open_pr(branch_name, title, task_id, deploy_url)
                    logger.info(f"PR: {pr_result.get('url', 'no url')}")
                except Exception as e:
                    logger.warning(f"PR error (non-fatal): {e}")

            # Step 9: Complete
            note = f"Completed by {self.cfg.agent_id} ({self.cfg.llm_model})"
            if deploy_url:
                note += f" | Deployed: {deploy_url}"
            self.hatchery.update_task_status(task_id, "done", comment=note)
            clear_task_context(self.cfg.agent_id)
            logger.info(f"[{self.cfg.agent_id}] Task DONE: {title}")

        except Exception as e:
            logger.error(f"Task FAILED [{task_id}]: {e}")
            try:
                self.hatchery.update_task_status(
                    task_id, "failed", comment=f"{self.cfg.agent_id} error: {e}"
                )
            except Exception:
                pass

        finally:
            self.current_task_id = None

    # ---- Git Helpers ----

    def _setup_repo(self, github_repo: str, branch_name: str) -> Optional[Path]:
        """Clone or pull the repo and create a feature branch."""
        if not github_repo:
            logger.warning("No github_repo in project — skipping git setup")
            return None
        try:
            repo_dir = self.git.clone_or_pull(github_repo)
            self.git.new_branch(branch_name)
            return repo_dir
        except Exception as e:
            logger.error(f"Git setup failed: {e}")
            raise

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

    # ---- Prompt Building ----

    def _build_prompt(self, title: str, description: str,
                      github_repo: str, repo_dir: Optional[Path],
                      task: dict) -> str:
        """
        Build the task prompt sent to the LLM brain.
        Includes repo structure, task description, and output format instructions.
        """
        repo_tree = ""
        if repo_dir and repo_dir.exists():
            try:
                tree_lines = []
                for root, dirs, files in os.walk(repo_dir):
                    # Skip common ignore dirs
                    dirs[:] = [d for d in dirs if d not in (
                        ".git", "node_modules", "__pycache__", ".next", ".nuxt",
                        "dist", "build", ".venv", "venv"
                    )]
                    for f in sorted(files)[:20]:  # cap at 20 per dir
                        rel = Path(root).relative_to(repo_dir)
                        tree_lines.append(f"  {rel}/{f}" if str(rel) != "." else f"  {f}")
                repo_tree = "\n".join(tree_lines[:100])  # max 100 lines
            except Exception as e:
                logger.warning(f"Could not build repo tree: {e}")

        return f"""You are an autonomous coding agent. Complete the task below.

## TASK
Title: {title}
Description: {description}

## REPOSITORY
URL: {github_repo}
{('Local structure:\n' + repo_tree) if repo_tree else ''}

## INSTRUCTIONS
1. Read existing files in the repo to understand the codebase
2. Make the necessary code changes to complete the task
3. Write all changed/created files using the format below
4. After writing files, run any build/test commands to verify correctness

## OUTPUT FORMAT
Always use JSON manifest format for file writes — it is unambiguous:

```json
{{
  "files": [
    {{
      "path": "src/app.ts",
      "content": "export default function App() {{ ... }}\n"
    }},
    {{
      "path": "src/styles.css",
      "content": ".app {{ color: red; }}\n"
    }}
  ]
}}
```

For file modifications, include the COMPLETE updated file content, not just the diff.

If no files need to be created or modified, respond with:
```json
{{"files": []}}
```

Do not include any explanatory text outside the JSON block.
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
