"""Smoke tests for GitManager (requires GITHUB_TOKEN env var)."""
import sys
import os
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.git_manager import GitManager


class TestGitManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = os.environ.get("GITHUB_TOKEN", "")
        if not cls.token:
            raise unittest.SkipTest("GITHUB_TOKEN not set")

    def test_init(self):
        """GitManager should initialize without errors."""
        gm = GitManager(github_token=self.token)
        self.assertIsNotNone(gm)

    def test_clone_public_repo(self):
        """Should clone a public repo without auth."""
        gm = GitManager(github_token="")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = gm.clone_or_pull(
                "https://github.com/wannanaplabs/toxic-clouds",
                target_dir=tmp / "test-clone"
            )
            self.assertTrue((tmp / "test-clone").exists())
            self.assertTrue((tmp / "test-clone" / ".git").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
