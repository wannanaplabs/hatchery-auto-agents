"""Smoke tests for Hatchery autonomous agents.

Run with: python3 -m pytest tests/ -v
Or directly: python3 tests/test_code_parser.py
"""
import sys
import os
import tempfile
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.base_agent import CodeParser


class TestCodeParser(unittest.TestCase):

    def setUp(self):
        self.repo_dir = Path(tempfile.mkdtemp())

    def test_json_manifest_single_file(self):
        """CodeParser should extract files from JSON manifest."""
        # Note: content strings use \\n to represent the two-character
        # sequence backslash-n (not a literal newline), so the resulting
        # JSON is valid when parsed.
        text = (
            '```json\n'
            '{"files": [{"path": "src/app.ts", "content": "export default function App() {\\n  return <div>Hello</div>;\\n}\\n"}]}\n'
            '```'
        )
        writes = CodeParser.parse(text, self.repo_dir)
        self.assertEqual(len(writes), 1)
        path = list(writes.keys())[0]
        self.assertEqual(path.name, "app.ts")
        self.assertIn("function App()", writes[path])

    def test_json_manifest_multiple_files(self):
        """CodeParser should extract multiple files from JSON manifest."""
        text = (
            '```json\n'
            '{"files": ['
            '{"path": "src/app.tsx", "content": "export default () => <App />;\\n"},'
            '{"path": "src/styles.css", "content": ".app { color: red; }\\n"},'
            '{"path": "README.md", "content": "# My App\\n"}'
            ']}\n'
            '```'
        )
        writes = CodeParser.parse(text, self.repo_dir)
        self.assertEqual(len(writes), 3)
        filenames = {p.name for p in writes.keys()}
        self.assertEqual(filenames, {"app.tsx", "styles.css", "README.md"})

    def test_fenced_block_with_path(self):
        """CodeParser should extract ```path/file.ext\\ncontent``` blocks."""
        text = '''
```src/hello.py
def hello():
    print("world")
```
'''
        writes = CodeParser.parse(text, self.repo_dir)
        self.assertEqual(len(writes), 1)
        path = list(writes.keys())[0]
        self.assertEqual(path.name, "hello.py")
        self.assertIn("def hello()", writes[path])

    def test_fenced_block_no_path_skipped(self):
        """CodeParser should NOT treat ```python\\ncontent``` as a file write."""
        text = '''
```python
def hello():
    pass
```
'''
        writes = CodeParser.parse(text, self.repo_dir)
        # "python" has no extension and no /, should be skipped
        # (CodeParser checks for extension or known config filenames)
        self.assertEqual(len(writes), 0)

    def test_create_directive(self):
        """CodeParser should extract CREATE: path\\n---\\ncontent blocks."""
        text = '''
CREATE: src/utils.ts
---
export const foo = () => "bar";
'''
        writes = CodeParser.parse(text, self.repo_dir)
        self.assertEqual(len(writes), 1)
        path = list(writes.keys())[0]
        self.assertEqual(path.name, "utils.ts")
        self.assertIn("foo", writes[path])

    def test_apply_writes_creates_file(self):
        """CodeParser.apply_writes() should write files to disk."""
        path = self.repo_dir / "test.txt"
        writes = {path: "hello world\n"}
        result = CodeParser.apply_writes(writes)
        self.assertEqual(len(result), 1)
        self.assertEqual(path.read_text(), "hello world\n")

    def test_apply_writes_creates_parent_dirs(self):
        """apply_writes should create parent directories automatically."""
        path = self.repo_dir / "nested" / "deep" / "file.txt"
        writes = {path: "deep content\n"}
        CodeParser.apply_writes(writes)
        self.assertEqual(path.read_text(), "deep content\n")

    def test_mixed_formats(self):
        """JSON manifest takes priority; fenced blocks supplement."""
        text = (
            '```json\n'
            '{"files": [{"path": "main.ts", "content": "// main\\n"}]}\n'
            '```\n\n'
            '```src/util.ts\n'
            '// util\n'
            '```'
        )
        writes = CodeParser.parse(text, self.repo_dir)
        self.assertEqual(len(writes), 2)
        filenames = {p.name for p in writes.keys()}
        self.assertEqual(filenames, {"main.ts", "util.ts"})

    def test_empty_manifest(self):
        """Empty JSON manifest should produce no writes."""
        text = '```json\n{"files": []}\n```'
        writes = CodeParser.parse(text, self.repo_dir)
        self.assertEqual(len(writes), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
