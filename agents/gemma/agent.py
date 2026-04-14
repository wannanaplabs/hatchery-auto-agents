"""
Gemma Agent — autonomous Hatchery worker powered by Google Gemma.

Supports two providers (selected via LLM_PROVIDER in config.env):
  - ollama (default, local): uses Ollama to run gemma3:* models locally
  - google: uses Google AI Studio API (requires GOOGLE_API_KEY)

Entry point: python -m agents.gemma.agent
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.base_agent import BaseAgent
from shared.llm_brain import LLMBrain
from shared.utils import setup_logging

logger = setup_logging("gemma-agent")


class GemmaAgent(BaseAgent):
    agent_type = "gemma"
    capabilities = [
        "simple-component", "config", "dark-theme", "readme", "bugfix",
    ]
    system_prompt = (
        "You are a precise autonomous coding agent. Your ONLY output is a JSON file manifest.\n\n"
        "RULES:\n"
        "1. Study the existing files provided in the prompt carefully\n"
        "2. Implement the task with minimal, focused changes\n"
        "3. Output ONLY a JSON block — no explanations before or after\n"
        "4. Write COMPLETE file contents, never partial snippets\n\n"
        "OUTPUT FORMAT (mandatory — your code will not be saved without this):\n"
        "```json\n"
        '{"files": [{"path": "relative/path.tsx", "content": "full file content"}]}\n'
        "```\n"
    )

    def create_brain(self):
        cfg = self.cfg
        provider = (cfg.llm_provider or "ollama").lower()
        if provider == "ollama":
            return LLMBrain.from_config(
                provider="ollama",
                api_key="",
                model=cfg.llm_model,  # e.g. "gemma3:4b"
                host=cfg.ollama_host,
            )
        # Fallback: Google AI Studio
        return LLMBrain.from_config(
            provider="google",
            api_key=cfg.google_api_key,
            model=cfg.llm_model,  # e.g. "gemma-3-27b"
        )


if __name__ == "__main__":
    import os
    env_file = os.environ.get("AGENT_ENV_FILE", "")
    agent = GemmaAgent(env_file=env_file if env_file else None)
    agent.run()
