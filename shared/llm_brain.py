"""Pluggable LLM brain — MiniMax, Ollama (Qwen/DeepSeek), Gemini, Claude Code CLI."""
import os
import json
import urllib.request
import urllib.error
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Base
# -----------------------------------------------------------------------

class LLMBrain(ABC):
    """Abstract LLM brain. Subclass for each provider."""

    @abstractmethod
    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 4096) -> str:
        """Send prompt + system to LLM, return text response."""
        ...

    @classmethod
    def from_config(cls, provider: str, api_key: str, model: str,
                    **kwargs) -> "LLMBrain":
        """Factory: pick the right brain class by provider name."""
        providers = {
            "minimax": MiniMaxBrain,
            "ollama": OllamaBrain,
            "google": GeminiBrain,
            "anthropic": ClaudeCodeBrain,
            "openai": OpenAIBrain,
        }
        if provider not in providers:
            raise ValueError(f"Unknown LLM provider: {provider}. "
                             f"Supported: {list(providers.keys())}")
        return providers[provider](api_key=api_key, model=model, **kwargs)

# -----------------------------------------------------------------------
# MiniMax
# -----------------------------------------------------------------------

class MiniMaxBrain(LLMBrain):
    def __init__(self, api_key: str, model: str,
                 base_url: str = "https://api.minimaxi.chat/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, system: str = "",
                max_tokens: int = 4096) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": (
                [{"role": "system", "content": system}] +
                [{"role": "user", "content": prompt}]
            ),
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body_err = e.read().decode() if e.fp else ""
            logger.error(f"MiniMax error {e.code}: {body_err[:300]}")
            raise

# -----------------------------------------------------------------------
# Ollama (Qwen / DeepSeek local)
# -----------------------------------------------------------------------

class OllamaBrain(LLMBrain):
    def __init__(self, api_key: str, model: str,
                 host: str = "0.0.0.0:11434"):
        self.api_key = api_key  # unused for local Ollama
        self.model = model
        self.host = host.rstrip("/")

    def complete(self, prompt: str, system: str = "",
                max_tokens: int = 4096) -> str:
        url = f"http://{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": (
                [{"role": "system", "content": system}] +
                [{"role": "user", "content": prompt}]
            ),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
                return data["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body_err = e.read().decode() if e.fp else ""
            logger.error(f"Ollama error {e.code}: {body_err[:300]}")
            raise

# -----------------------------------------------------------------------
# Google AI Studio — Gemma
# -----------------------------------------------------------------------

class GeminiBrain(LLMBrain):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model  # e.g. "gemma-3-27b"

    def complete(self, prompt: str, system: str = "",
                max_tokens: int = 4096) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/"
            f"v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]} if system else None,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body_err = e.read().decode() if e.fp else ""
            logger.error(f"Gemini error {e.code}: {body_err[:300]}")
            raise

# -----------------------------------------------------------------------
# Anthropic — Claude Code CLI
# -----------------------------------------------------------------------

class ClaudeCodeBrain(LLMBrain):
    """
    Claude Code CLI brain with two modes:

    1. Agent mode (default): Runs `claude -p` in the repo directory with full
       agent capabilities — file reading, writing, shell execution, iteration.
       Claude Code handles files directly; no CodeParser needed.

    2. Print mode (fallback): Runs `claude --print` for single-shot text
       generation when agent mode is not needed.

    Set `agentic=True` (default) for agent mode.
    """
    def __init__(self, api_key: str, model: str,
                 mcp_config: Optional[str] = None,
                 agentic: bool = True,
                 timeout: int = 600):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.mcp_config = mcp_config
        self.agentic = agentic
        # Flag so BaseAgent knows this brain writes files itself
        self.is_agentic = agentic
        self.timeout = timeout  # 10 min default for agentic tasks
        self._env = os.environ.copy()
        self._cwd = None  # Set by BaseAgent before calling complete()

    def set_cwd(self, cwd: str):
        """Set working directory for agent mode (repo directory)."""
        self._cwd = cwd

    def complete(self, prompt: str, system: str = "",
                max_tokens: int = 4096) -> str:
        if self.agentic:
            return self._complete_agentic(prompt, system)
        return self._complete_print(prompt, system)

    def _complete_agentic(self, prompt: str, system: str = "") -> str:
        """
        Run Claude Code in full agent mode (-p flag).
        Claude reads files, writes code, runs commands, iterates on errors.
        Returns the conversation output (for logging/status only — files
        are already written to disk by Claude).
        """
        import subprocess

        # Build the task prompt — system prompt becomes part of the instruction
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n---\n\n{full_prompt}"

        cmd = [
            "claude",
            "-p",                              # Non-interactive mode (still has full tool access)
            "--dangerously-skip-permissions",   # Autonomous — no confirmation prompts
            "--output-format", "text",
            "--model", self.model,
        ]
        if self.mcp_config:
            cmd += ["--mcp-config", self.mcp_config]

        env = self._env.copy()
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key

        cwd = self._cwd or os.getcwd()
        logger.info(f"Claude Code agent mode: cwd={cwd}, timeout={self.timeout}s")

        try:
            proc = subprocess.run(
                cmd,
                input=full_prompt.encode(),
                capture_output=True,
                timeout=self.timeout,
                env=env,
                cwd=cwd,
            )
            stdout = proc.stdout.decode().strip()
            stderr = proc.stderr.decode().strip()

            if proc.returncode != 0:
                logger.error(f"Claude Code agent failed (rc={proc.returncode}): "
                             f"{stderr[:500]}")
            else:
                logger.info(f"Claude Code agent completed ({len(stdout)} chars output)")

            if stderr:
                logger.debug(f"Claude Code stderr: {stderr[:300]}")

            return stdout

        except subprocess.TimeoutExpired:
            logger.error(f"Claude Code agent timed out after {self.timeout}s")
            raise

    def _complete_print(self, prompt: str, system: str = "") -> str:
        """Fallback: single-shot text generation via --print."""
        import subprocess

        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{full_prompt}"

        cmd = [
            "claude", "--print",
            "--dangerously-skip-permissions",
            "--output-format", "text",
            "--model", self.model,
        ]
        if self.mcp_config:
            cmd += ["--mcp-config", self.mcp_config]

        env = self._env.copy()
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key

        try:
            proc = subprocess.run(
                cmd,
                input=full_prompt.encode(),
                capture_output=True, timeout=120,
                env=env,
                cwd=self._cwd,
            )
            if proc.returncode != 0:
                logger.error(f"Claude Code stderr: {proc.stderr.decode()[:200]}")
            return proc.stdout.decode().strip()
        except subprocess.TimeoutExpired:
            logger.error("Claude Code --print timed out")
            raise

# -----------------------------------------------------------------------
# OpenAI (backup)
# -----------------------------------------------------------------------

class OpenAIBrain(LLMBrain):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, system: str = "",
                max_tokens: int = 4096) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": (
                [{"role": "system", "content": system}] +
                [{"role": "user", "content": prompt}]
            ),
            "max_tokens": max_tokens,
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body_err = e.read().decode() if e.fp else ""
            logger.error(f"OpenAI error {e.code}: {body_err[:300]}")
            raise
