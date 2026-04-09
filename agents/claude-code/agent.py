"""
Claude Code Agent — autonomous Hatchery worker powered by Claude Sonnet 4
via the Claude Code CLI (--print mode).

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
    system_prompt = (
        "You are an expert autonomous coding agent. "
        "Use the Claude Code CLI to read files, navigate the codebase, write code, "
        "run commands, and complete the assigned task. "
        "After making changes, verify the build succeeds with `npm run build` or equivalent. "
        "Report all file changes using the JSON manifest format."
    )

    def create_brain(self):
        cfg = self.cfg
        # Find Claude Code MCP config if present
        mcp_config = os.environ.get("CLAUDE_MCP_CONFIG", "")
        if not mcp_config:
            # Default Claude Desktop MCP config location on Mac
            default_mcp = Path.home() / ".claude" / "claude_desktop_config.json"
            if default_mcp.exists():
                mcp_config = str(default_mcp)

        return LLMBrain.from_config(
            provider="anthropic",
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=cfg.llm_model,
            mcp_config=mcp_config,
        )


if __name__ == "__main__":
    env_file = os.environ.get("AGENT_ENV_FILE", "")
    agent = ClaudeCodeAgent(env_file=env_file if env_file else None)
    agent.run()
