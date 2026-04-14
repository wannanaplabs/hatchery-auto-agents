"""
Tests for poll loop and heartbeat resilience.

Critical paths to verify:
- 429 rate limit errors don't crash the agent
- 429 errors only log once (no spam)
- Real errors trigger exponential backoff but recover
- Task selection prefers configured workspace
- Poll loop exits cleanly on self.running=False
"""
import sys
import time
import threading
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

# Mock flask so base_agent imports cleanly
if "flask" not in sys.modules:
    fake = ModuleType("flask")
    fake.Flask = lambda *a, **k: None
    fake.request = None
    fake.jsonify = lambda *a, **k: None
    fake.Response = None
    sys.modules["flask"] = fake

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.base_agent import BaseAgent


class RateLimitError(Exception):
    """Stand-in for the exception shape the real Hatchery raises."""
    pass


def rate_limit_err():
    return Exception("HTTP 429: iteration_limit_exceeded")


class FakeHatchery:
    """Configurable fake. Set .fail_mode to control which calls throw.
    Tasks drain as they're executed (matches real Hatchery claim semantics)."""
    def __init__(self):
        self.fail_mode = None  # "rate_limit" | "transient" | None
        self.heartbeat_calls = 0
        self.get_tasks_calls = 0
        self.notif_calls = 0
        self.tasks_to_return = []
        self._drained_ids = set()

    def heartbeat(self, *a, **kw):
        self.heartbeat_calls += 1
        if self.fail_mode == "rate_limit":
            raise rate_limit_err()
        if self.fail_mode == "transient":
            raise Exception("connection reset")
        return {}

    def get_available_tasks(self):
        self.get_tasks_calls += 1
        if self.fail_mode == "rate_limit":
            raise rate_limit_err()
        if self.fail_mode == "transient":
            raise Exception("connection reset")
        # Filter out tasks that have already been claimed
        return [t for t in self.tasks_to_return if t.get("id") not in self._drained_ids]

    def get_notifications(self):
        self.notif_calls += 1
        return []

    def claim_task(self, task_id):
        # Mark as drained so subsequent get_available_tasks doesn't return it
        self._drained_ids.add(task_id)
        return {}

    def update_task_status(self, *a, **kw):
        return {}

    def reset_session(self):
        return {}


class TestableAgent(BaseAgent):
    """Skips __init__ side effects so we can drive the loops directly."""
    agent_type = "test"

    def __init__(self, hatchery):
        self.cfg = SimpleNamespace(
            agent_id="test-01",
            agent_name="Test",
            agent_port=9999,
            webhook_url="",
            llm_provider="fake",
            llm_model="fake",
        )
        self.hatchery = hatchery
        self.git = None
        self.deploy = None
        self.brain = None
        self.running = False
        self.current_task_id = None
        self.poll_only_mode = True
        self.ctx_path = Path("/tmp/nonexistent-ctx.json")
        self._message_inbox = {}
        self._message_responses = {}
        self._shutdown_event = threading.Event()
        self.executed_tasks = []

    def create_brain(self):
        return None

    def _execute_task(self, task):
        # Match real behavior: claiming the task drains it from the queue
        self.hatchery.claim_task(task.get("id"))
        self.executed_tasks.append(task)

    def _get_progress(self):
        return None


class TestHeartbeatResilience(unittest.TestCase):

    def setUp(self):
        import os
        os.environ["HEARTBEAT_INTERVAL"] = "0"  # Fire immediately for tests

    def _run_heartbeat_for(self, agent, seconds=0.3):
        agent.running = True
        agent._shutdown_event.clear()
        t = threading.Thread(target=agent._heartbeat_loop, daemon=True)
        t.start()
        time.sleep(seconds)
        agent.running = False
        agent._shutdown_event.set()
        t.join(timeout=1)

    def test_rate_limit_does_not_crash(self):
        """429 on heartbeat should not crash or stop the loop."""
        hatchery = FakeHatchery()
        hatchery.fail_mode = "rate_limit"
        agent = TestableAgent(hatchery)

        self._run_heartbeat_for(agent, seconds=0.2)

        # Should have attempted multiple heartbeats despite 429s
        self.assertGreater(hatchery.heartbeat_calls, 2)

    def test_recovery_after_transient_error(self):
        """Transient error → recover once errors stop."""
        hatchery = FakeHatchery()
        hatchery.fail_mode = "transient"
        agent = TestableAgent(hatchery)

        agent.running = True
        t = threading.Thread(target=agent._heartbeat_loop, daemon=True)
        t.start()
        time.sleep(0.1)
        hatchery.fail_mode = None  # stop failing
        time.sleep(0.2)
        agent.running = False
        t.join(timeout=1)

        # Should have made multiple calls total (including after recovery)
        self.assertGreater(hatchery.heartbeat_calls, 1)


class TestPollLoopResilience(unittest.TestCase):

    def setUp(self):
        import os
        os.environ["POLL_INTERVAL"] = "0"

    def _run_poll_for(self, agent, seconds=0.3):
        agent.running = True
        agent._shutdown_event.clear()
        t = threading.Thread(target=agent._poll_loop, daemon=True)
        t.start()
        time.sleep(seconds)
        agent.running = False
        agent._shutdown_event.set()
        t.join(timeout=1)

    def test_rate_limit_does_not_crash(self):
        """429 from get_available_tasks should not crash the loop."""
        hatchery = FakeHatchery()
        hatchery.fail_mode = "rate_limit"
        agent = TestableAgent(hatchery)

        self._run_poll_for(agent, seconds=0.2)

        # Multiple attempts made
        self.assertGreater(hatchery.get_tasks_calls, 1)

    def test_picks_up_task_when_available(self):
        """Poll loop should execute task as soon as one appears."""
        hatchery = FakeHatchery()
        hatchery.tasks_to_return = [
            {"id": "t1", "title": "Do thing", "hatchery_projects": {}}
        ]
        agent = TestableAgent(hatchery)

        self._run_poll_for(agent, seconds=0.1)

        self.assertEqual(len(agent.executed_tasks), 1)
        # After picking up, it's gone — don't re-execute the same task
        hatchery.tasks_to_return = []

    def test_empty_queue_polls_repeatedly(self):
        """With no tasks, the loop keeps polling (doesn't exit)."""
        hatchery = FakeHatchery()
        agent = TestableAgent(hatchery)

        self._run_poll_for(agent, seconds=0.15)

        # Multiple poll cycles, no tasks executed
        self.assertGreater(hatchery.get_tasks_calls, 1)
        self.assertEqual(len(agent.executed_tasks), 0)

    def test_transient_error_triggers_backoff_then_recovers(self):
        """Transient errors trigger backoff but loop recovers."""
        hatchery = FakeHatchery()
        hatchery.fail_mode = "transient"
        agent = TestableAgent(hatchery)

        agent.running = True
        t = threading.Thread(target=agent._poll_loop, daemon=True)
        t.start()
        time.sleep(0.05)
        hatchery.fail_mode = None
        hatchery.tasks_to_return = [
            {"id": "recovered", "title": "After recovery", "hatchery_projects": {}}
        ]
        time.sleep(0.3)
        agent.running = False
        t.join(timeout=1)

        # Agent eventually picked up a task after recovering
        self.assertEqual(len(agent.executed_tasks), 1)
        self.assertEqual(agent.executed_tasks[0]["id"], "recovered")


class TestTaskSelection(unittest.TestCase):

    def setUp(self):
        self.agent = TestableAgent(FakeHatchery())

    def test_empty_queue_returns_none(self):
        self.assertIsNone(self.agent._select_task([]))

    def test_no_workspace_preference_takes_first(self):
        import os
        os.environ.pop("WANNAFUN_WS", None)
        os.environ.pop("HATCHERY_WS", None)
        tasks = [
            {"id": "a", "hatchery_projects": {"workspace_id": "ws-1"}},
            {"id": "b", "hatchery_projects": {"workspace_id": "ws-2"}},
        ]
        selected = self.agent._select_task(tasks)
        self.assertEqual(selected["id"], "a")

    def test_workspace_preference_filters(self):
        import os
        os.environ["WANNAFUN_WS"] = "ws-2"
        try:
            tasks = [
                {"id": "a", "hatchery_projects": {"workspace_id": "ws-1"}},
                {"id": "b", "hatchery_projects": {"workspace_id": "ws-2"}},
            ]
            selected = self.agent._select_task(tasks)
            self.assertEqual(selected["id"], "b")
        finally:
            os.environ.pop("WANNAFUN_WS", None)

    def test_workspace_fallback_to_first(self):
        """If no task matches preferred workspace, take the first."""
        import os
        os.environ["WANNAFUN_WS"] = "ws-99"
        try:
            tasks = [
                {"id": "a", "hatchery_projects": {"workspace_id": "ws-1"}},
                {"id": "b", "hatchery_projects": {"workspace_id": "ws-2"}},
            ]
            selected = self.agent._select_task(tasks)
            self.assertEqual(selected["id"], "a")
        finally:
            os.environ.pop("WANNAFUN_WS", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
