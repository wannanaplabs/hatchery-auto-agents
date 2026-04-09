"""
Gemma Agent — autonomous Hatchery worker powered by Google Gemma 3 via Google AI Studio.

Entry point: python -m agents.gemma.agent
Requires: GOOGLE_API_KEY env var with access to Gemma via ai.google.dev API.
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
    system_prompt = (
        "You are a precise autonomous coding agent powered by Google Gemma 3. "
        "Analyze the task requirements carefully before writing any code. "
        "First explore the repository structure using `ls`, `cat`, and `find` commands. "
        "Then implement the solution, keeping changes minimal and focused. "
        "Report all file changes using the JSON manifest format with complete file contents. "
        "After implementing, verify the code is correct by running build commands."
    )

    def create_brain(self):
        cfg = self.cfg
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
