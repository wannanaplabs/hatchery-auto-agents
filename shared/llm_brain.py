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
            with urllib.request.urlopen(req, timeout=60) as resp:
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
            with urllib.request.urlopen(req, timeout=120) as resp:
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
    """Uses `claude --print` to pipe prompts through Claude Code CLI."""
    def __init__(self, api_key: str, model: str, mcp_config: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.mcp_config = mcp_config  # path to hatchery MCP config
        self._env = os.environ.copy()

    def complete(self, prompt: str, system: str = "",
                max_tokens: int = 4096) -> str:
        # Build the full prompt with system instruction
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{full_prompt}"

        cmd = [
            "claude", "--print",
            "--dangerously-skip-permissions",
            f"--output-format=text",
            "--model", self.model,
        ]
        if self.mcp_config:
            cmd += ["--mcp-config", self.mcp_config]

        import subprocess
        env = self._env.copy()
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key

        try:
            proc = subprocess.run(
                cmd,
                input=full_prompt.encode(),
                capture_output=True, timeout=60,
                env=env,
            )
            if proc.returncode != 0:
                logger.error(f"Claude Code stderr: {proc.stderr.decode()[:200]}")
            return proc.stdout.decode().strip()
        except subprocess.TimeoutExpired:
            logger.error("Claude Code timed out after 60s")
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
