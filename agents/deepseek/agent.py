"""
DeepSeek Agent — autonomous Hatchery worker powered by DeepSeek V3 via local Ollama.

Entry point: python -m agents.deepseek.agent
Requires: Ollama running at 0.0.0.0:11434 with deepseek-v3 (or configured model).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.base_agent import BaseAgent
from shared.llm_brain import LLMBrain
from shared.utils import setup_logging

logger = setup_logging("deepseek-agent")


class DeepSeekAgent(BaseAgent):
    agent_type = "deepseek"
    system_prompt = (
        "You are an expert autonomous coding agent. Your ONLY output is a JSON file manifest.\n\n"
        "RULES:\n"
        "1. Study the existing files provided in the prompt\n"
        "2. Implement the task by writing complete, working files\n"
        "3. Output ONLY a JSON block — no explanations before or after\n"
        "4. Write COMPLETE file contents, never partial snippets\n"
        "5. If the repo is empty, scaffold the full project\n\n"
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
            model=cfg.llm_model,  # e.g. "deepseek-v3"
            host=cfg.ollama_host,
        )


if __name__ == "__main__":
    import os
    env_file = os.environ.get("AGENT_ENV_FILE", "")
    agent = DeepSeekAgent(env_file=env_file if env_file else None)
    agent.run()
