"""Require Herdr's explicit success report, including on versions that exit zero on failure."""

import subprocess
from pathlib import Path


def native_check(herdr, folder):
    folder = Path(folder).resolve()
    result = subprocess.run([str(herdr), "check", str(folder)], check=True,
                            capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", flush=True)
    if f"check passed: {folder}" not in result.stdout.splitlines():
        raise SystemExit(f"Native check did not pass: {folder}")
