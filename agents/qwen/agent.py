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
    system_prompt = (
        "You are a precise autonomous coding agent powered by Qwen 3. "
        "Analyze the task, understand the existing codebase, implement the solution, "
        "and report file changes using the JSON manifest format. "
        "Use `ls`, `cat`, and shell commands to explore the repo. "
        "After writing code, verify it works by running build/test commands. "
        "Qwen is very good at following instructions precisely — be explicit about paths "
        "and file contents in your output."
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
