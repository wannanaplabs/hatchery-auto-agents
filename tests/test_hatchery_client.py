"""Smoke tests for HatcheryClient (requires HATCHERY_API_KEY env var)."""
import sys
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.hatchery_client import HatcheryClient


class TestHatcheryClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.api_key = os.environ.get("HATCHERY_API_KEY", "")
        if not cls.api_key:
            raise unittest.SkipTest("HATCHERY_API_KEY not set")

    def test_client_creation(self):
        """HatcheryClient should create with api key."""
        client = HatcheryClient(api_key=self.api_key)
        self.assertEqual(client.api_key, self.api_key)

    def test_get_available_tasks(self):
        """get_available_tasks should return a list."""
        client = HatcheryClient(api_key=self.api_key)
        tasks = client.get_available_tasks()
        self.assertIsInstance(tasks, list)

    def test_update_task_status_dry_run(self):
        """update_task_status should not raise on valid call."""
        client = HatcheryClient(api_key=self.api_key)
        try:
            result = client.update_task_status("fake-task-id-12345", "in_progress")
            self.assertIsInstance(result, dict)
        except Exception as e:
            # Network errors are OK in test environment
            self.assertIsInstance(e, (ConnectionError, TimeoutError, OSError))


if __name__ == "__main__":
    unittest.main(verbosity=2)
