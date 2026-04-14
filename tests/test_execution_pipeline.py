"""
Integration tests for the new task execution pipeline.

Tests both paths:
- Agentic: brain.is_agentic=True, brain writes files directly
- Single-shot: brain returns JSON manifest, retries on parse/build failures

Uses a FakeBrain to avoid real LLM API calls.

Run: python3 -m unittest tests.test_execution_pipeline -v
"""
import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

# Mock flask
if "flask" not in sys.modules:
    fake = ModuleType("flask")
    fake.Flask = lambda *a, **k: None
    fake.request = None
    fake.jsonify = lambda *a, **k: None
    fake.Response = None
    sys.modules["flask"] = fake

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.base_agent import BaseAgent, CodeParser


class FakeBrain:
    """Fake LLM brain for testing. Returns canned responses."""
    def __init__(self, responses, is_agentic=False):
        self.responses = list(responses)  # queue
        self.calls = []  # record of (prompt, system) tuples
        self.is_agentic = is_agentic

    def complete(self, prompt, system="", max_tokens=4096):
        self.calls.append((prompt, system))
        if not self.responses:
            return ""
        return self.responses.pop(0)

    def set_cwd(self, cwd):
        self.cwd = cwd


class FakeHatchery:
    """Fake Hatchery client — records calls, no HTTP."""
    def __init__(self):
        self.status_updates = []
        self.claims = []

    def claim_task(self, task_id):
        self.claims.append(task_id)

    def update_task_status(self, task_id, status, comment="", progress_pct=None):
        self.status_updates.append({
            "task_id": task_id,
            "status": status,
            "comment": comment,
            "progress_pct": progress_pct,
        })

    def broadcast(self, content, message_type="fyi"):
        pass  # No-op in tests


class TestableAgent(BaseAgent):
    """
    BaseAgent subclass that skips __init__ side effects (no env, no HatcheryClient,
    no webhook, no git). Lets us drive _execute_task directly with fake deps.
    """
    agent_type = "test"
    system_prompt = "Test system prompt"

    def __init__(self, brain, repo_dir):
        # Bypass the normal init
        from types import SimpleNamespace
        self.cfg = SimpleNamespace(
            agent_id="test-01",
            agent_name="Test Agent",
            llm_provider="fake",
            llm_model="fake-model",
        )
        self.brain = brain
        self.hatchery = FakeHatchery()
        self.git = None  # Not used in tests
        self.deploy = None
        self.current_task_id = None
        self.running = True
        self._repo_dir_override = repo_dir
        self._commits = []
        self._pushed = False
        self._team_updates = []
        self._message_inbox = {}
        self._message_responses = {}
        self._shutdown_event = __import__('threading').Event()

    def create_brain(self):
        return self.brain

    # Override git/deploy steps so tests don't need a real repo
    def _setup_repo(self, repo_url, branch_name, project):
        return self._repo_dir_override

    def _commit_and_push(self, commit_msg, task_id):
        self._commits.append(commit_msg)
        self._pushed = True

    def _try_deploy(self, project, repo_dir, pushed):
        return ""

    def _try_open_pr(self, branch_name, title, task_id, deploy_url):
        pass

    def _claim_task(self, task_id):
        self.hatchery.claim_task(task_id)

    def _update_progress(self, task_id, status, pct, comment=""):
        pass  # Silent in tests


class TestSingleShotPipeline(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.task = {
            "id": "task-123",
            "title": "Create a hello world file",
            "description": "Add greet.txt with 'hello'",
            "hatchery_projects": {
                "name": "Test Project",
                "repo_url": "",
            },
        }

    def _good_response(self):
        return (
            '```json\n'
            '{"files": [{"path": "greet.txt", "content": "hello\\n"}]}\n'
            '```'
        )

    def test_first_try_success(self):
        """Single-shot with valid JSON on first try writes files and marks done."""
        brain = FakeBrain([self._good_response()])
        agent = TestableAgent(brain, self.repo)
        agent._execute_task(self.task)

        # File should exist
        self.assertTrue((self.repo / "greet.txt").exists())
        self.assertEqual((self.repo / "greet.txt").read_text(), "hello\n")

        # Should have been called once (no retry needed)
        self.assertEqual(len(brain.calls), 1)

        # Task should be marked done
        done_updates = [u for u in agent.hatchery.status_updates if u["status"] == "done"]
        self.assertEqual(len(done_updates), 1)

    def test_empty_response_triggers_retry(self):
        """Empty LLM response should trigger retry with feedback."""
        brain = FakeBrain(["", self._good_response()])
        agent = TestableAgent(brain, self.repo)
        agent._execute_task(self.task)

        # Should have retried
        self.assertEqual(len(brain.calls), 2)
        # Second call should have feedback about empty response
        second_prompt = brain.calls[1][0]
        self.assertIn("empty", second_prompt.lower())
        # File still created
        self.assertTrue((self.repo / "greet.txt").exists())

    def test_no_files_parsed_triggers_retry(self):
        """Response with no parseable JSON triggers retry with feedback."""
        brain = FakeBrain([
            "Sure, I'll help with that task.",  # No JSON block
            self._good_response(),
        ])
        agent = TestableAgent(brain, self.repo)
        agent._execute_task(self.task)

        # Should have retried
        self.assertEqual(len(brain.calls), 2)
        # Feedback should mention JSON manifest
        second_prompt = brain.calls[1][0]
        self.assertIn("JSON manifest", second_prompt)
        # File created on retry
        self.assertTrue((self.repo / "greet.txt").exists())

    def test_all_attempts_fail_releases_task(self):
        """If all 3 attempts fail to parse, task is released back to ready (not marked done)."""
        brain = FakeBrain([
            "Not JSON.",
            "Still not JSON.",
            "Also not JSON.",
        ])
        agent = TestableAgent(brain, self.repo)
        agent._execute_task(self.task)

        # 3 attempts made
        self.assertEqual(len(brain.calls), 3)
        # No file created
        self.assertFalse((self.repo / "greet.txt").exists())
        # Task released back to ready — NOT marked done with placeholder code
        ready_updates = [u for u in agent.hatchery.status_updates if u["status"] == "ready"]
        self.assertEqual(len(ready_updates), 1)
        # No done status
        done_updates = [u for u in agent.hatchery.status_updates if u["status"] == "done"]
        self.assertEqual(len(done_updates), 0)

    def test_build_failure_retry_with_errors(self):
        """Build failure on attempt 1 triggers retry with error output."""
        # Create a package.json with a build script that fails the first time
        bad_json = (
            '```json\n'
            '{"files": [{"path": "package.json", "content": '
            '"{\\"name\\": \\"x\\", \\"scripts\\": {\\"build\\": \\"exit 1\\"}}"}]}\n'
            '```'
        )
        good_json = (
            '```json\n'
            '{"files": [{"path": "package.json", "content": '
            '"{\\"name\\": \\"x\\", \\"scripts\\": {\\"build\\": \\"echo ok\\"}}"}]}\n'
            '```'
        )
        brain = FakeBrain([bad_json, good_json])
        agent = TestableAgent(brain, self.repo)
        agent._execute_task(self.task)

        # Should have retried after build failure
        self.assertEqual(len(brain.calls), 2)
        # Second call should have build error feedback
        second_prompt = brain.calls[1][0]
        self.assertIn("PREVIOUS ATTEMPT FAILED", second_prompt)


class TestAgenticPipeline(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.task = {
            "id": "task-agentic",
            "title": "Test agentic task",
            "description": "Agent handles file writing itself",
            "hatchery_projects": {
                "name": "Agentic Test",
                "repo_url": "",
            },
        }

    def test_agentic_skips_codeparser(self):
        """Agentic brain should bypass CodeParser — the brain is expected to write files itself."""
        # Simulate the agent writing a file itself (as Claude Code would)
        def fake_complete(prompt, system="", max_tokens=4096):
            (self.repo / "agent-wrote-this.txt").write_text("done by agent\n")
            return "Task completed."

        brain = FakeBrain(["Task completed."], is_agentic=True)
        brain.complete = fake_complete  # override to simulate file write

        agent = TestableAgent(brain, self.repo)
        agent._execute_task(self.task)

        # File should exist (written by the brain, not CodeParser)
        self.assertTrue((self.repo / "agent-wrote-this.txt").exists())

        # Task marked done
        done_updates = [u for u in agent.hatchery.status_updates if u["status"] == "done"]
        self.assertEqual(len(done_updates), 1)
        # Note should mention agentic mode
        self.assertIn("agentic", done_updates[0]["comment"])

    def test_agentic_sets_cwd(self):
        """BaseAgent should call set_cwd on agentic brains before completing."""
        calls = {"set_cwd": None}

        class TrackingBrain(FakeBrain):
            def set_cwd(self, cwd):
                calls["set_cwd"] = cwd

        brain = TrackingBrain(["Done"], is_agentic=True)
        agent = TestableAgent(brain, self.repo)
        agent._execute_task(self.task)

        self.assertEqual(calls["set_cwd"], str(self.repo))


if __name__ == "__main__":
    unittest.main(verbosity=2)
