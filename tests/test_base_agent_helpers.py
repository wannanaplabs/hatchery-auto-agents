"""
Tests for the new BaseAgent helper methods:
- _read_key_files: reads key files from repo into prompt context
- _get_repo_tree: builds directory tree string
- _detect_build_command: detects the right build command for a repo
- _run_build: runs a build command and captures output

Run: python3 -m unittest tests.test_base_agent_helpers -v
Or:  python3 tests/test_base_agent_helpers.py
"""
import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

# Mock flask since tests don't need a real webhook server
if "flask" not in sys.modules:
    fake_flask = ModuleType("flask")
    fake_flask.Flask = lambda *a, **k: None
    fake_flask.request = None
    fake_flask.jsonify = lambda *a, **k: None
    fake_flask.Response = None
    sys.modules["flask"] = fake_flask

# Project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.base_agent import BaseAgent


class DummyAgent(BaseAgent):
    """Minimal BaseAgent subclass that skips __init__ for helper method tests."""

    def __init__(self):
        # Skip the full BaseAgent init — we only need the helper methods
        pass

    def create_brain(self):
        return None


class TestReadKeyFiles(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.agent = DummyAgent()

    def test_empty_repo_returns_empty_string(self):
        result = self.agent._read_key_files(self.repo)
        self.assertEqual(result, "")

    def test_reads_readme(self):
        (self.repo / "README.md").write_text("# My Project\nHello world\n")
        result = self.agent._read_key_files(self.repo)
        self.assertIn("README.md", result)
        self.assertIn("Hello world", result)

    def test_reads_package_json(self):
        pkg = {"name": "my-app", "scripts": {"build": "next build"}}
        (self.repo / "package.json").write_text(json.dumps(pkg))
        result = self.agent._read_key_files(self.repo)
        self.assertIn("package.json", result)
        self.assertIn("my-app", result)

    def test_reads_multiple_files(self):
        (self.repo / "README.md").write_text("# Test\n")
        (self.repo / "package.json").write_text('{"name": "x"}')
        (self.repo / "tsconfig.json").write_text('{"compilerOptions": {}}')
        result = self.agent._read_key_files(self.repo)
        self.assertIn("README.md", result)
        self.assertIn("package.json", result)
        self.assertIn("tsconfig.json", result)

    def test_reads_nested_app_pages(self):
        app_dir = self.repo / "src" / "app"
        app_dir.mkdir(parents=True)
        (app_dir / "page.tsx").write_text("export default function Page() { return <div/>; }\n")
        (app_dir / "layout.tsx").write_text("export default function Layout({children}) { return children; }\n")
        result = self.agent._read_key_files(self.repo)
        self.assertIn("page.tsx", result)
        self.assertIn("layout.tsx", result)

    def test_truncates_large_files(self):
        # Single file >3000 chars should be truncated
        large_content = "x" * 5000
        (self.repo / "README.md").write_text(large_content)
        result = self.agent._read_key_files(self.repo)
        # Should be truncated somewhere — won't include all 5000 chars
        self.assertIn("truncated", result)

    def test_total_char_cap(self):
        # Create many files that would exceed total 15k cap
        for i, fname in enumerate([
            "README.md", "package.json", "tsconfig.json",
            "next.config.js", "vite.config.js"
        ]):
            (self.repo / fname).write_text("x" * 3000)
        result = self.agent._read_key_files(self.repo)
        # Should respect ~15k cap
        self.assertLess(len(result), 20000)


class TestGetRepoTree(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.agent = DummyAgent()

    def test_empty_repo(self):
        tree = self.agent._get_repo_tree(self.repo)
        self.assertEqual(tree, "")

    def test_lists_files(self):
        (self.repo / "a.txt").write_text("")
        (self.repo / "b.txt").write_text("")
        tree = self.agent._get_repo_tree(self.repo)
        self.assertIn("a.txt", tree)
        self.assertIn("b.txt", tree)

    def test_skips_ignored_dirs(self):
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.ts").write_text("")
        (self.repo / "node_modules").mkdir()
        (self.repo / "node_modules" / "should-not-appear.js").write_text("")
        (self.repo / ".git").mkdir()
        (self.repo / ".git" / "HEAD").write_text("")
        tree = self.agent._get_repo_tree(self.repo)
        self.assertIn("app.ts", tree)
        self.assertNotIn("should-not-appear", tree)
        self.assertNotIn("HEAD", tree)


class TestDetectBuildCommand(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.agent = DummyAgent()

    def test_no_build_system_returns_none(self):
        result = self.agent._detect_build_command(self.repo)
        self.assertIsNone(result)

    def test_npm_build_preferred(self):
        pkg = {"scripts": {"build": "next build", "test": "jest", "lint": "eslint"}}
        (self.repo / "package.json").write_text(json.dumps(pkg))
        # No node_modules → includes npm install prefix
        self.assertEqual(self.agent._detect_build_command(self.repo), "npm install && npm run build")

    def test_npm_build_without_install_if_node_modules_exists(self):
        pkg = {"scripts": {"build": "next build"}}
        (self.repo / "package.json").write_text(json.dumps(pkg))
        (self.repo / "node_modules").mkdir()
        # node_modules exists → no install prefix
        self.assertEqual(self.agent._detect_build_command(self.repo), "npm run build")

    def test_typecheck_fallback(self):
        pkg = {"scripts": {"typecheck": "tsc --noEmit", "lint": "eslint"}}
        (self.repo / "package.json").write_text(json.dumps(pkg))
        self.assertEqual(self.agent._detect_build_command(self.repo), "npm install && npm run typecheck")

    def test_lint_fallback(self):
        pkg = {"scripts": {"lint": "eslint"}}
        (self.repo / "package.json").write_text(json.dumps(pkg))
        self.assertEqual(self.agent._detect_build_command(self.repo), "npm install && npm run lint")

    def test_npm_install_if_no_scripts(self):
        pkg = {"name": "no-scripts", "dependencies": {}}
        (self.repo / "package.json").write_text(json.dumps(pkg))
        self.assertEqual(self.agent._detect_build_command(self.repo), "npm install")

    def test_cargo(self):
        (self.repo / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n')
        self.assertEqual(self.agent._detect_build_command(self.repo), "cargo check")

    def test_pyproject(self):
        (self.repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
        result = self.agent._detect_build_command(self.repo)
        self.assertIsNotNone(result)
        self.assertIn("py_compile", result)


class TestRunBuild(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.agent = DummyAgent()

    def test_no_command_returns_ok(self):
        result = self.agent._run_build(self.repo)
        self.assertTrue(result["ok"])

    def test_successful_command(self):
        result = self.agent._run_build(self.repo, command="echo hello")
        self.assertTrue(result["ok"])
        self.assertIn("hello", result["output"])

    def test_failing_command(self):
        result = self.agent._run_build(self.repo, command="exit 1")
        self.assertFalse(result["ok"])

    def test_captures_stderr(self):
        result = self.agent._run_build(
            self.repo, command="echo 'err msg' >&2; exit 1"
        )
        self.assertFalse(result["ok"])
        self.assertIn("err msg", result["output"])

    def test_output_capped(self):
        # Generate >5000 chars of output
        result = self.agent._run_build(
            self.repo, command="python3 -c \"print('x'*10000)\""
        )
        self.assertTrue(result["ok"])
        self.assertLessEqual(len(result["output"]), 5000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
