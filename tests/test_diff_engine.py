import unittest

from src.core.diff_engine import compute_diff, unified_patch


class TestDiffEngine(unittest.TestCase):
    def test_compute_diff_basic(self):
        left = "one\ntwo\nthree\n"
        right = "one\nTWO\nthree\nfour\n"
        rows = compute_diff(left, right, ignore_ws=True, ignore_case=False, normalize_eol=True, inline=True)
        tags = {r.tag for r in rows}
        self.assertIn("replace", tags)
        self.assertIn("insert", tags)
        # ensure line numbers present for some rows
        self.assertTrue(any(r.left_no is not None for r in rows))
        self.assertTrue(any(r.right_no is not None for r in rows))

    def test_unified_patch(self):
        a = "a\nb\n"
        b = "a\nbb\n"
        patch = unified_patch(a, b, "left", "right")
        self.assertIn("--- left", patch)
        self.assertIn("+++ right", patch)
        self.assertIn("+bb", patch)


if __name__ == "__main__":
    unittest.main()

