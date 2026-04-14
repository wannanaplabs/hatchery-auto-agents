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
    capabilities = [
        "scaffold", "config", "dark-theme", "simple-component",
        "recharts-chart", "api-route", "readme", "bugfix",
    ]
    system_prompt = (
        "You are an autonomous coding agent. Your ONLY job is to output complete file contents.\n\n"
        "CRITICAL RULES:\n"
        "1. You MUST output a JSON manifest wrapped in ```json code fences\n"
        "2. ALWAYS create files — never say 'nothing to do'\n"
        "3. If the repo is empty, scaffold the ENTIRE project from scratch\n"
        "4. Write COMPLETE file contents, not snippets or placeholders\n"
        "5. Include ALL necessary files: package.json, tsconfig.json, configs, source\n"
        "6. Do NOT output explanatory text — ONLY the JSON block\n\n"
        "OUTPUT FORMAT (you MUST use this exact format):\n"
        "```json\n"
        '{"files": [{"path": "package.json", "content": "..."}, '
        '{"path": "src/app/page.tsx", "content": "..."}]}\n'
        "```\n"
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
