"""
MiniMax Agent — autonomous Hatchery worker powered by MiniMax M2.5.

Entry point: python -m agents.minimax.agent
Or via: docker compose run minimax-agent
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.base_agent import BaseAgent
from shared.llm_brain import LLMBrain
from shared.types import AgentConfig
from shared.utils import setup_logging

logger = setup_logging("minimax-agent")


class MinimaxAgent(BaseAgent):
    agent_type = "minimax"
    system_prompt = (
        "You are a precise, autonomous coding agent. "
        "Read the task, understand the existing codebase, implement the solution, "
        "and report all file changes using the JSON manifest format. "
        "Focus on correctness, clarity, and minimal changes that fully satisfy the task. "
        "When done, run `npm build` or equivalent to verify the code compiles."
    )

    def create_brain(self):
        cfg = self.cfg
        return LLMBrain.from_config(
            provider="minimax",
            api_key=cfg.minimax_api_key,
            model=cfg.llm_model,
            base_url=cfg.minimax_base_url,
        )


if __name__ == "__main__":
    import os
    env_file = os.environ.get("AGENT_ENV_FILE", "")
    agent = MinimaxAgent(env_file=env_file if env_file else None)
    agent.run()
