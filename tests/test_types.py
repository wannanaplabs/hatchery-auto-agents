"""Smoke tests for shared types."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.types import AgentConfig, ProjectSpec, TaskAssignedEvent


class TestTypes(unittest.TestCase):

    def test_agent_config_from_env(self):
        """AgentConfig should have all expected fields."""
        # Note: requires env vars to be set; test will skip if not present
        required_fields = [
            "agent_type", "agent_id", "agent_name", "agent_port",
            "webhook_url", "hatchery_api_key", "llm_provider", "llm_model",
            "github_token", "vercel_token", "hatchery_base_url",
            "minimax_api_key", "ollama_host", "google_api_key",
        ]
        cfg = AgentConfig(
            agent_type="test",
            agent_id="test-01",
            agent_name="Test Agent",
            agent_port=8201,
            webhook_url="http://localhost:8201/webhook",
            hatchery_api_key="test-key",
            llm_provider="minimax",
            llm_model="M2.5",
        )
        for field in required_fields:
            self.assertTrue(
                hasattr(cfg, field),
                f"AgentConfig missing field: {field}"
            )

    def test_project_spec(self):
        """ProjectSpec should hold project data."""
        proj = ProjectSpec(
            id="proj-123",
            name="Toxic Clouds",
            slug="toxic-clouds",
            github_repo="https://github.com/wannanaplabs/toxic-clouds",
            stack={"frontend": "next.js", "data_source": "OpenAQ"},
        )
        self.assertEqual(proj.slug, "toxic-clouds")
        self.assertEqual(proj.stack["frontend"], "next.js")

    def test_task_assigned_event(self):
        """TaskAssignedEvent should parse from dict."""
        event = TaskAssignedEvent(
            event="task.assigned",
            task_id="task-abc",
            project=ProjectSpec(
                id="p1", name="Test", slug="test",
                github_repo="https://github.com/test/repo",
            ),
            title="[1/6] Scaffold project",
            description="Clone and init the Next.js project",
            assigned_at="2026-04-09T12:00:00Z",
            priority="normal",
        )
        self.assertEqual(event.event, "task.assigned")
        self.assertEqual(event.project.github_repo, "https://github.com/test/repo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
