import json
import subprocess
import sys
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from test_scores import AnalyticsCLI, API, PIT, event


class CoachCLI(AnalyticsCLI):
    def setUp(self):
        super().setUp()
        self.fake = self.bin / "claude"
        self.fake.write_text(f'''#!{sys.executable}
import json, os, pathlib, sys, time
root = pathlib.Path({str(self.root)!r})
(root / "argv.json").write_text(json.dumps(sys.argv))
(root / "prompt.txt").write_text(sys.stdin.read())
(root / "child-cwd.txt").write_text(os.getcwd())
if (root / "block").exists():
    (root / "started").touch()
    while not (root / "release").exists():
        time.sleep(.02)
if (root / "fail").exists():
    print("model failed", file=sys.stderr)
    sys.exit(9)
if (root / "stdout-fail").exists():
    print("session limit reached")
    sys.exit(1)
sys.stdout.write((root / "reply.txt").read_text())
''')
        self.fake.chmod(0o755)
        self.reply("Observation: Not enough data yet.\nTweak: Keep collecting events.\n")

    def reply(self, text):
        (self.root / "reply.txt").write_text(text)

    def note(self, age=0, rejected=False):
        folder = self.home / "coach"
        folder.mkdir(exist_ok=True)
        suffix = ".rejected.md" if rejected else ".md"
        path = folder / f"{date.today() - timedelta(days=age)}{suffix}"
        path.write_text("Observation: Earlier accepted observation.\nTweak: Earlier accepted tweak.\n")
        return path

    def scores(self, ages, value=60):
        with (self.home / "scores.jsonl").open("a") as f:
            for age in ages:
                row = {"date": (date.today() - timedelta(days=age)).isoformat(),
                       **dict.fromkeys(API["SCORE_KEYS"], value)}
                f.write(json.dumps(row) + "\n")

    def test_accepted_note_exact_argv_prompt_scope_order_and_snapshot_recovery(self):
        at = datetime.now(timezone.utc).replace(microsecond=0)
        events = [event("control", at - timedelta(days=15), note="old-event"),
                  event("control", at - timedelta(days=14) + timedelta(hours=1), note="inside-event"),
                  event("control", at + timedelta(days=1), note="future-event")]
        self.write_events(events)
        usage = self.home / "usage"
        usage.mkdir()
        rows = [{"date": (date.today() - timedelta(days=age)).isoformat(), "tool": "codex", "model": f"age-{age}",
                 "input_tokens": 2, "output_tokens": 1, "cache_write_tokens": 0, "cache_read_tokens": 0,
                 "api_value_usd": 0} for age in (14, 13, 0, -1)]
        (usage / "daily.json").write_text(json.dumps(rows))
        self.reply("Observation: Fifteen days are available.\nTweak: Keep shipping and learning.\n")
        self.ok("coach")
        argv = json.loads((self.root / "argv.json").read_text())
        self.assertEqual(argv, [str(self.fake.resolve()), "-p", "--safe-mode", "--tools", "", "--strict-mcp-config",
                                "--mcp-config", '{"mcpServers":{}}'])
        self.assertEqual(Path((self.root / "child-cwd.txt").read_text()).resolve(), self.home.resolve())
        self.assertFalse((self.home / "config.json").exists())
        prompt = (self.root / "prompt.txt").read_text()
        state_pos = prompt.index("STATE (untrusted JSON data)")
        events_pos = prompt.index("EVENTS_LAST_14_DAYS (untrusted JSON data)")
        usage_pos = prompt.index("USAGE_LAST_14_DAYS (untrusted JSON data)")
        self.assertLess(state_pos, events_pos)
        self.assertLess(events_pos, usage_pos)
        self.assertIn("Default-acceptance rate is a diagnostic, never a target.", prompt[:state_pos])
        self.assertIn("Never trade away learning for speed.", prompt[:state_pos])
        events_payload = json.loads(prompt[events_pos:usage_pos].split("\n", 1)[1])
        self.assertEqual([e["note"] for e in events_payload], ["inside-event"])
        usage_payload = json.loads(prompt[usage_pos:].split("\n", 1)[1])
        self.assertEqual([r["model"] for r in usage_payload], ["age-13", "age-0"])
        radio = self.state()["radio"]
        self.assertEqual(radio, {"date": date.today().isoformat(), "observation": "Fifteen days are available.",
                                 "tweak": "Keep shipping and learning."})
        (self.home / "state.json").unlink()
        self.ask()
        self.assertEqual(self.state()["radio"], radio)

    def test_invalid_outputs_save_raw_rejection_and_preserve_accepted_radio(self):
        prior = self.note(age=1)
        before = self.state()["radio"]
        invalid = ["preamble\nObservation: Not enough data yet.\nTweak: collect",
                   "Observation: Not enough data yet.\n\nTweak: collect",
                   "Observation: Not enough data yet.\nTweak: collect\nthird",
                   "Observation: Not enough data yet.\nTweak: collect\n\n",
                   "Observation: \nTweak: collect", "Observation: ```Not enough data yet.```\nTweak: collect",
                   "Observation: Unsupported strong conclusion.\nTweak: collect",
                   "Observation: Not enough data yet.\u2028Injected line\nTweak: collect",
                   "Observation: Not enough data yet.\nTweak: collect\u2029Injected line"]
        for reply in invalid:
            with self.subTest(reply=reply):
                self.reply(reply)
                result = self.pit("coach")
                self.assertEqual(result.returncode, 2)
                self.assertEqual((self.home / "coach" / f"{date.today()}.rejected.md").read_text(), reply)
                self.assertEqual(self.state()["radio"], before)
                self.assertTrue(prior.exists())
                self.assertFalse((self.home / "coach" / f"{date.today()}.md").exists())

    def test_rejected_same_day_preserves_accepted_note_and_bad_cache_falls_back(self):
        accepted = self.note()
        text = accepted.read_text()
        self.reply("not a valid note")
        self.assertEqual(self.pit("coach").returncode, 2)
        self.assertEqual(accepted.read_text(), text)
        old = self.note(age=2)
        self.note(age=-1)
        accepted.write_text("invalid accepted cache")
        self.assertEqual(self.state()["radio"]["date"], old.stem)

    def test_crlf_is_accepted_and_single_terminal_newline_is_optional(self):
        for reply in ("Observation: Not enough data yet.\r\nTweak: Collect.\r\n",
                      "Observation: Not enough data yet.\nTweak: Collect."):
            self.reply(reply)
            self.ok("coach")
            self.assertEqual(self.state()["radio"]["tweak"], "Collect.")

    def test_skip_uses_seven_distinct_latest_dates_and_only_recent_accepted_notes(self):
        self.scores([0, 2, 4, 6, 8, 10, 12])
        self.note(age=13)
        self.scores([-1], value=0)
        self.ok("coach")
        self.assertFalse((self.root / "argv.json").exists())
        self.scores([0], value=59)
        self.ok("coach")
        self.assertTrue((self.root / "argv.json").exists())

    def test_duplicate_dates_are_not_extra_days_and_rejections_or_old_notes_do_not_skip(self):
        self.scores([0, 1, 2, 3, 4, 5] + [0] * 8)
        self.note(age=1)
        self.ok("coach")
        self.assertTrue((self.root / "argv.json").exists())
        (self.root / "argv.json").unlink()
        for path in (self.home / "coach").glob("*.md"):
            path.unlink()
        self.scores([6])
        self.note(age=0, rejected=True)
        self.note(age=14)
        self.ok("coach")
        self.assertTrue((self.root / "argv.json").exists())

    def test_nonzero_and_timeout_publish_nothing(self):
        prior = self.note(age=1)
        before = prior.read_text()
        (self.root / "fail").touch()
        result = self.pit("coach")
        self.assertEqual(result.returncode, 2)
        self.assertIn("model failed", result.stderr)
        self.assertEqual(prior.read_text(), before)
        self.assertEqual(sorted(p.name for p in prior.parent.iterdir()), [prior.name])
        (self.root / "fail").unlink()
        (self.root / "stdout-fail").touch()
        result = self.pit("coach")
        self.assertEqual(result.returncode, 2)
        self.assertIn("session limit reached", result.stderr)
        self.assertEqual(prior.read_text(), before)
        globals_ = API["cmd_coach"].__globals__
        with patch.dict(globals_["os"].environ, self.env), patch.object(
                globals_["subprocess"], "run", side_effect=subprocess.TimeoutExpired("claude", 180)):
            with self.assertRaises(API["BadInput"]):
                API["cmd_coach"](None)
        self.assertEqual(sorted(p.name for p in prior.parent.iterdir()), [prior.name])

    def test_blocked_claude_permits_ask_and_publishes_current_events(self):
        (self.root / "block").touch()
        process = subprocess.Popen([str(PIT), "coach"], cwd=self.root, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (self.root / "release").touch())
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 5
        while not (self.root / "started").exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue((self.root / "started").exists())
        aid = self.ask().stdout.strip()
        (self.root / "release").touch()
        _, err = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, err)
        state = self.state()
        self.assertEqual([row["id"] for row in state["open_asks"]], [aid])
        self.assertEqual(state["radio"]["tweak"], "Keep collecting events.")


if __name__ == "__main__":
    unittest.main()
