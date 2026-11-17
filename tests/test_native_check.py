import runpy
import io
from contextlib import redirect_stdout
import sys
import tempfile
import unittest
from pathlib import Path


native_check = runpy.run_path(str(Path(__file__).resolve().parent.parent /
                                "scripts/herdr_check.py"))["native_check"]


class NativeCheck(unittest.TestCase):
    def run_checker(self, body):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            executable = root / "herdr"
            executable.write_text(f"#!{sys.executable}\nimport sys\n" + body)
            executable.chmod(0o755)
            with redirect_stdout(io.StringIO()):
                native_check(executable, root)

    def test_explicit_native_success_is_accepted(self):
        self.run_checker('print("check passed: " + sys.argv[2])\n')

    def test_native_failure_with_zero_exit_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.run_checker('print("render failed\\ncheck failed: " + sys.argv[2])\n')

    def test_empty_success_exit_is_not_proof(self):
        with self.assertRaises(SystemExit):
            self.run_checker('pass\n')


if __name__ == "__main__":
    unittest.main()
