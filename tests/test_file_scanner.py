import unittest
import os
import shutil
from pathlib import Path

from src.core.file_scanner import FileScanner


class TestFileScanner(unittest.TestCase):
    def setUp(self):
        self.base = Path("tests/_tmp_scan")
        if self.base.exists():
            shutil.rmtree(self.base)
        (self.base / "venv").mkdir(parents=True, exist_ok=True)
        (self.base / "src").mkdir(parents=True, exist_ok=True)
        (self.base / "src" / "keep.py").write_text("print('ok')\n", encoding="utf-8")
        (self.base / "src" / "skip.log").write_text("log\n", encoding="utf-8")
        (self.base / "README.md").write_text("# readme\n", encoding="utf-8")
        # .gitignore: ignore README.md
        (self.base / ".gitignore").write_text("README.md\n", encoding="utf-8")

    def tearDown(self):
        if self.base.exists():
            shutil.rmtree(self.base)

    def test_scanner_filters(self):
        sc = FileScanner(str(self.base))
        sc.apply_gitignore = True
        sc.excluded_folder_names = {"venv"}
        sc.excluded_folders = {"src/missing"}
        sc.excluded_file_patterns = {"*.log"}
        sc.excluded_files = set()

        got = {(rel, t) for (_, rel, t) in sc.yield_files()}
        # Normalize to POSIX-style for cross-platform assertions
        rels = {r.replace('\\', '/') for (r, _) in got}
        # venv ignored by name
        self.assertNotIn("venv", "/".join(rels))
        # pattern excludes log
        self.assertNotIn("src/skip.log", rels)
        # gitignore excludes README.md
        self.assertNotIn("README.md", rels)
        # keep Python file present
        self.assertIn("src/keep.py", rels)


if __name__ == "__main__":
    unittest.main()
