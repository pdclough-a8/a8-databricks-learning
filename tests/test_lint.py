"""Keep notebooks and library code to the same lint standard as ordinary Python."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LintTests(unittest.TestCase):
    def test_ruff_checks_course_code(self):
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "lib", "notebooks", "tests"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
