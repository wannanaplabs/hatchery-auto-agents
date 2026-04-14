"""
Claude Code Agent — autonomous Hatchery worker powered by Claude Code CLI
in full agent mode.

Unlike other agents that use single-shot LLM calls, this agent runs Claude Code
as a real agent: it reads files, writes code, runs commands, iterates on errors,
and produces working code directly in the repo.

Entry point: python -m agents.claude-code.agent
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.base_agent import BaseAgent
from shared.llm_brain import LLMBrain
from shared.utils import setup_logging

logger = setup_logging("claude-code-agent")


class ClaudeCodeAgent(BaseAgent):
    agent_type = "claude-code"
    capabilities = [
        "complex-ui", "3d-visualization", "d3-force", "web-audio", "react-leaflet",
        "svg-chart", "full-page-build", "debugging", "refactoring", "api-integration",
        "scaffold", "config", "dark-theme", "simple-component", "recharts-chart",
        "api-route", "bugfix", "readme",
    ]
    system_prompt = (
        "You are an expert autonomous coding agent working on a real codebase.\n\n"
        "WORKFLOW:\n"
        "1. Explore the repo — read key files to understand the project structure\n"
        "2. Plan your approach — identify which files to create or modify\n"
        "3. Implement — write complete, production-quality code\n"
        "4. Verify — run the build/test commands and fix any errors\n"
        "5. Ensure ALL files are saved before finishing\n\n"
        "RULES:\n"
        "- Write COMPLETE files, not snippets or placeholders\n"
        "- If the repo is empty, scaffold the full project (package.json, configs, source)\n"
        "- Always run `npm install` after adding dependencies\n"
        "- Always run the build command to verify your code compiles\n"
        "- Fix build errors — do not leave broken code\n"
    )

    def create_brain(self):
        cfg = self.cfg
        mcp_config = os.environ.get("CLAUDE_MCP_CONFIG", "")
        if not mcp_config:
            default_mcp = Path.home() / ".claude" / "claude_desktop_config.json"
            if default_mcp.exists():
                mcp_config = str(default_mcp)

        return LLMBrain.from_config(
            provider="anthropic",
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=cfg.llm_model,
            mcp_config=mcp_config,
            agentic=True,     # Full agent mode — reads/writes/executes directly
            timeout=600,      # 10 minutes for complex tasks
        )


if __name__ == "__main__":
    env_file = os.environ.get("AGENT_ENV_FILE", "")
    agent = ClaudeCodeAgent(env_file=env_file if env_file else None)
    agent.run()
