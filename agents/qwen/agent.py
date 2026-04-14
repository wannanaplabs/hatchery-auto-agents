"""
Qwen Agent — autonomous Hatchery worker powered by Qwen 3 via local Ollama.

Entry point: python -m agents.qwen.agent
Requires: Ollama running at 0.0.0.0:11434 with qwen3:14b (or configured model).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.base_agent import BaseAgent
from shared.llm_brain import LLMBrain
from shared.utils import setup_logging

logger = setup_logging("qwen-agent")


class QwenAgent(BaseAgent):
    agent_type = "qwen"
    capabilities = [
        "simple-component", "config", "dark-theme", "api-route", "readme", "bugfix",
    ]
    system_prompt = (
        "You are a precise autonomous coding agent. Your ONLY output is a JSON file manifest.\n\n"
        "RULES:\n"
        "1. Study the existing files provided in the prompt\n"
        "2. Implement the task by writing complete files\n"
        "3. Output ONLY a JSON block — no explanations before or after\n"
        "4. Write COMPLETE file contents, never partial snippets\n\n"
        "OUTPUT FORMAT (mandatory — your code will not be saved without this):\n"
        "```json\n"
        '{"files": [{"path": "relative/path.tsx", "content": "full file content"}]}\n'
        "```\n"
    )

    def create_brain(self):
        cfg = self.cfg
        return LLMBrain.from_config(
            provider="ollama",
            api_key="",  # Ollama local — no API key
            model=cfg.llm_model,  # e.g. "qwen3:14b"
            host=cfg.ollama_host,
        )


if __name__ == "__main__":
    import os
    env_file = os.environ.get("AGENT_ENV_FILE", "")
    agent = QwenAgent(env_file=env_file if env_file else None)
    agent.run()
