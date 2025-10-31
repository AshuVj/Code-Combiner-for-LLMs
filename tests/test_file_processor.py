import unittest
import os
import shutil
from pathlib import Path

from src.core.file_processor import FileProcessor


class TestFileProcessor(unittest.TestCase):
    def setUp(self):
        self.base = Path("tests/_tmp_proc")
        if self.base.exists():
            shutil.rmtree(self.base)
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "a.txt").write_text("hello\n", encoding="utf-8")
        (self.base / "b.py").write_text("print('x')\n", encoding="utf-8")
        # binary-like file
        (self.base / "c.bin").write_bytes(b"\x00\x01\x02")

    def tearDown(self):
        if self.base.exists():
            shutil.rmtree(self.base)

    def test_process_mixed(self):
        fp = FileProcessor(str(self.base))
        files = [
            ("a.txt", "a.txt", "text"),
            ("b.py", "b.py", "text"),
            ("c.bin", "c.bin", "binary"),
        ]
        out = self.base / "out.txt"
        ok = fp.process_files(files, str(out))
        self.assertTrue(ok)
        txt = out.read_text(encoding="utf-8")
        self.assertIn("File: a.txt", txt)
        self.assertIn("hello", txt)
        self.assertIn("File: c.bin", txt)
        self.assertIn("Binary file - content not included", txt)


if __name__ == "__main__":
    unittest.main()

