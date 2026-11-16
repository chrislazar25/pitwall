import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_scores import AnalyticsCLI, PIT


class HealthCLI(AnalyticsCLI):
    def git(self, repo, *args, age=0):
        stamp = (datetime.now(timezone.utc) - timedelta(days=age)).isoformat()
        env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
               "GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME": "Test",
               "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

    def repo(self, name, age=None):
        repo = self.root / name
        repo.mkdir()
        self.git(repo, "init", "-q")
        if age is not None:
            self.git(repo, "commit", "-q", "--allow-empty", "-m", "test", age=age)
        return repo

    def projects(self, projects):
        (self.home / "projects.json").write_text(json.dumps({k: str(v) for k, v in projects.items()}))

    def fake_git(self):
        real = shutil.which("git")
        fake = self.bin / "git"
        fake.write_text(f'''#!{sys.executable}
import json, os, pathlib, sys, time
root = pathlib.Path({str(self.root)!r})
if sys.argv[1:2] == ["rev-list"]:
    (root / "git-argv.json").write_text(json.dumps(sys.argv[1:]))
    if (root / "block").exists():
        (root / "started").touch()
        while not (root / "release").exists():
            time.sleep(.02)
    if (root / "fail").exists():
        sys.exit(9)
os.execv({real!r}, [{real!r}, *sys.argv[1:]])
''')
        fake.chmod(0o755)

    def test_root_flags_real_git_recent_old_unborn_nonrepo_and_deleted(self):
        recent = self.repo("recent", age=8)
        self.git(recent, "commit", "-q", "--allow-empty", "-m", "newer", age=1)
        (recent / ".github" / "workflows").mkdir(parents=True)
        (recent / ".github" / "workflows" / "build.yaml").write_text("name: test")
        (recent / "__tests__").mkdir()
        (recent / "README.rst").write_text("readme")
        old = self.repo("old", age=15)
        (old / "tests").write_text("file")
        (old / "README-directory").mkdir()
        (old / ".github" / "workflows" / "nested").mkdir(parents=True)
        (old / ".github" / "workflows" / "nested" / "ignored.yml").write_text("name: nested")
        unborn = self.repo("unborn")
        plain = self.root / "plain"
        plain.mkdir()
        self.projects({"recent": recent, "old": old, "unborn": unborn, "plain": plain, "deleted": self.root / "gone"})
        self.ok("health")
        rows = self.state()["garage"]
        self.assertEqual(rows, [
            {"project": "old", "ci": False, "tests": False, "readme": False, "active": False, "commits_7d": 0},
            {"project": "plain", "ci": False, "tests": False, "readme": False, "active": False, "commits_7d": 0},
            {"project": "recent", "ci": True, "tests": True, "readme": True, "active": True, "commits_7d": 1},
            {"project": "unborn", "ci": False, "tests": False, "readme": False, "active": False, "commits_7d": 0},
        ])
        self.ask()
        self.assertEqual(self.state()["garage"], rows)
        (self.home / "state.json").unlink()
        self.assertEqual(self.state()["garage"], rows)

    def test_process_failure_preserves_prior_garage(self):
        repo = self.repo("demo", age=1)
        self.projects({"demo": repo})
        self.ok("health")
        before = (self.home / "garage.json").read_text()
        self.fake_git()
        (self.root / "fail").touch()
        result = self.pit("health")
        self.assertEqual(result.returncode, 2)
        self.assertIn("git health collection failed", result.stderr)
        self.assertEqual((self.home / "garage.json").read_text(), before)
        self.assertEqual(json.loads((self.root / "git-argv.json").read_text()),
                         ["rev-list", "--count", "--since=7 days ago", "HEAD"])

    def test_blocked_git_permits_ask_and_publication_uses_current_events(self):
        repo = self.repo("demo", age=1)
        self.projects({"demo": repo})
        self.fake_git()
        (self.root / "block").touch()
        process = subprocess.Popen([str(PIT), "health"], cwd=self.root, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (self.root / "release").touch())
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 5
        while not (self.root / "started").exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue((self.root / "started").exists())
        result = self.ask()
        aid = result.stdout.strip()
        (self.root / "release").touch()
        _, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, err)
        state = self.state()
        self.assertEqual([row["id"] for row in state["open_asks"]], [aid])
        self.assertEqual(state["garage"][0]["commits_7d"], 1)


if __name__ == "__main__":
    unittest.main()
