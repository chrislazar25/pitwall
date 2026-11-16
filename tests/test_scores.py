import json
import os
import runpy
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PIT = Path(__file__).resolve().parent.parent / "pit"
API = runpy.run_path(str(PIT))
AT = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def stamp(at):
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def event(kind, at, **fields):
    return {"kind": kind, "ts": stamp(at), **fields}


def ask_events(aid, answered, seconds, needed=True):
    return [event("ask", answered - timedelta(seconds=seconds), id=aid, type="context",
                  agent="codex", project="demo", headline=aid),
            event("answer", answered, id=aid, needed=needed)]


def lap_events(lid, shipped, seconds):
    return [event("lap_start", shipped - timedelta(seconds=seconds), lap=lid, project="demo", title=lid),
            event("lap_ship", shipped, lap=lid)]


class Scores(unittest.TestCase):
    def scores(self, events):
        return API["calculate_scores"](events, AT)

    def test_fixed_speed_cases(self):
        for minutes, expected in ((5, 100), (62.5, 50), (120, 0), (200, 0)):
            with self.subTest(minutes=minutes):
                self.assertEqual(self.scores(ask_events("a", AT, minutes * 60))["speed"], expected)

    def test_fixed_quality_includes_ever_reopened_even_when_open(self):
        events = []
        for i in range(4):
            events += ask_events(str(i), AT - timedelta(hours=1), 300, needed=i != 0)
        events.append(event("reopen", AT, id="1"))
        self.assertEqual(self.scores(events)["ask_quality"], 50)

    def baseline(self, seconds=36000, count=10):
        return [e for i in range(count) for e in lap_events(str(i), AT - timedelta(days=20, hours=-i), seconds)]

    def test_fixed_shipping_cases(self):
        for hours, expected in ((5, 100), (10, 50), (20, 25)):
            self.assertEqual(self.scores(self.baseline() + lap_events("current", AT, hours * 3600))["shipping"], expected)
        self.assertIsNone(self.scores(self.baseline(count=8) + lap_events("current", AT, 36000))["shipping"])
        self.assertIsNone(self.scores(self.baseline())["shipping"])

    def test_first_ten_shipping_ties_follow_ship_events_rather_than_start_order(self):
        durations = [("last", 100)] + [(str(i), 10 if i < 5 else 1) for i in range(10)]
        events = [lap_events(lid, AT, hours * 3600)[0] for lid, hours in durations]
        events += [event("lap_ship", AT, lap=str(i)) for i in range(10)]
        events.append(event("lap_ship", AT, lap="last"))
        self.assertEqual(self.scores(events)["shipping"], 28)

    def test_fixed_ownership_and_latest_current_stock(self):
        events = [event("concept", AT - timedelta(days=40), project="demo", name=str(i), must_own=True,
                        status="passed" if i < 2 else "not_passed") for i in range(3)]
        self.assertEqual(self.scores(events)["ownership"], 67)
        events.append(event("concept", AT, project="demo", name="2", must_own=False, status="not_passed"))
        self.assertEqual(self.scores(events)["ownership"], 100)
        events.append(event("concept", AT + timedelta(seconds=1), project="demo", name="0", must_own=True, status="not_passed"))
        self.assertEqual(self.scores(events)["ownership"], 100)

    def test_unique_latest_answer_cohort_old_start_and_inclusive_window(self):
        events = ask_events("old", AT - timedelta(days=7), 300)
        events += ask_events("repeat", AT - timedelta(days=8), 300)
        events += [event("reopen", AT - timedelta(days=6), id="repeat"),
                   event("answer", AT, id="repeat", needed=False)]
        events += ask_events("outside", AT - timedelta(days=7, seconds=1), 300)
        events += [event("ask", AT, id="open", type="context", agent="a", project="demo", headline="open")]
        self.assertEqual(self.scores(events)["ask_quality"], 50)
        self.assertEqual(self.scores(events)["speed"], 0)

    def test_future_reopen_answer_ship_and_concept_do_not_change_as_of_score(self):
        events = ask_events("a", AT - timedelta(hours=1), 300)
        events += self.baseline() + lap_events("current", AT, 36000)
        expected = self.scores(events)
        events += [event("reopen", AT + timedelta(seconds=1), id="a"),
                   event("answer", AT + timedelta(seconds=2), id="a", needed=False),
                   event("lap_ship", AT + timedelta(seconds=1), lap="current"),
                   event("concept", AT + timedelta(seconds=1), project="demo", name="x", must_own=True, status="passed")]
        self.assertEqual(self.scores(events), expected)

    def test_full_precision_then_half_up_and_zero_shipping(self):
        events = ask_events("a", AT - timedelta(hours=1), 3715) + ask_events("b", AT, 3716)
        self.assertEqual(self.scores(events)["speed"], 51)
        self.assertEqual(self.scores(self.baseline(seconds=59) + lap_events("current", AT, 119))["shipping"], 25)
        self.assertEqual(self.scores(self.baseline() + lap_events("current", AT, 0))["shipping"], 100)
        self.assertIsNone(self.scores(self.baseline(seconds=0) + lap_events("current", AT, 0))["shipping"])
        self.assertEqual(self.scores([]), dict.fromkeys(API["SCORE_KEYS"]))


class AnalyticsCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "pitwall"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "PITWALL_HOME": str(self.home),
                    "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", "")}

    def pit(self, *args, timeout=10):
        return subprocess.run([str(PIT), *args], cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=timeout)

    def ok(self, *args):
        result = self.pit(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def state(self):
        return json.loads(self.ok("state").stdout)

    def write_events(self, events):
        (self.home / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    def ask(self):
        return self.ok("ask", "--type", "context", "--agent", "codex", "--headline", "still responsive", "--reason", "test")


class ScoreCLI(AnalyticsCLI):
    def test_score_history_last_valid_physical_row_per_date_and_future_ignored(self):
        today = date.today().isoformat()
        path = self.home / "scores.jsonl"
        row = {"date": today, **dict.fromkeys(API["SCORE_KEYS"], 80)}
        path.write_text(json.dumps(row) + "\n" + json.dumps({**row, "speed": 20}) + "\nBAD\n"
                        + json.dumps({**row, "speed": -1}) + "\n"
                        + json.dumps({**row, "date": (date.today() + timedelta(days=1)).isoformat(), "speed": 100}) + "\n")
        self.assertEqual(self.state()["scores"], {**dict.fromkeys(API["SCORE_KEYS"], 80), "speed": 20})
        self.ok("score")
        self.assertEqual(self.state()["scores"], dict.fromkeys(API["SCORE_KEYS"]))
        self.assertEqual(len(path.read_text().splitlines()), 6)

    def test_sources_recover_after_snapshot_deleted_and_survive_core_event(self):
        self.write_events([event("concept", datetime.now(timezone.utc) - timedelta(days=30),
                                 project="demo", name="ownership", must_own=True, status="passed")])
        self.ok("score")
        garage = [{"project": "demo", "ci": True, "tests": False, "readme": True, "active": False, "commits_7d": 0}]
        (self.home / "garage.json").write_text(json.dumps(garage))
        notes = self.home / "coach"
        notes.mkdir()
        (notes / f"{date.today()}.md").write_text("Observation: saved observation\nTweak: saved tweak\n")
        before = self.state()
        self.assertEqual(before["scores"]["ownership"], 100)
        (self.home / "state.json").unlink()
        self.ask()
        after = self.state()
        for key in ("scores", "garage", "radio"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after["garage"], garage)
        self.assertEqual(len(after["open_asks"]), 1)

    def test_malformed_optional_analytics_never_break_core_append(self):
        (self.home / "scores.jsonl").write_text("false\n{broken\n")
        (self.home / "garage.json").write_text('{"bad":true}')
        notes = self.home / "coach"
        notes.mkdir()
        (notes / f"{date.today()}.md").write_text("garbage")
        result = self.ask()
        self.assertIn("garage unavailable", result.stderr)
        self.assertIn("ignored", result.stderr)
        state = self.state()
        self.assertEqual(len(state["open_asks"]), 1)
        self.assertEqual(state["garage"], [])
        self.assertIsNone(state["radio"])
        self.assertEqual(state["scores"], dict.fromkeys(API["SCORE_KEYS"]))


if __name__ == "__main__":
    unittest.main()
