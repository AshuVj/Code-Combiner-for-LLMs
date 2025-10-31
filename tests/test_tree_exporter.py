import unittest
import os
import shutil
from pathlib import Path

from src.core.tree_exporter import TreeExporter


class TestTreeExporter(unittest.TestCase):
    def setUp(self):
        self.base = Path("tests/_tmp_tree")
        if self.base.exists():
            shutil.rmtree(self.base)
        (self.base / "a/b").mkdir(parents=True, exist_ok=True)
        (self.base / "node_modules").mkdir(parents=True, exist_ok=True)
        (self.base / "a" / "keep.txt").write_text("hello", encoding="utf-8")
        (self.base / "a" / "drop.log").write_text("log", encoding="utf-8")
        (self.base / "node_modules" / "x.txt").write_text("nm", encoding="utf-8")

    def tearDown(self):
        if self.base.exists():
            shutil.rmtree(self.base)

    def test_export_respects_exclusions(self):
        exporter = TreeExporter(
            str(self.base),
            excluded_folder_names={"node_modules"},
            excluded_folders={"a/b/doesntmatter"},
            excluded_file_patterns={"*.log"},
            excluded_files=set(),
        )
        lines = exporter.build_lines(style="ascii", include_sizes=False, markdown=True)
        text = "\n".join(lines)
        self.assertIn("keep.txt", text)
        self.assertNotIn("drop.log", text)
        self.assertNotIn("node_modules", text)
        self.assertTrue(text.startswith("```text"))
        self.assertTrue(text.rstrip().endswith("```"))


if __name__ == "__main__":
    unittest.main()

