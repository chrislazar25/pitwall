import json
import os
import runpy
import subprocess
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PIT = Path(__file__).resolve().parent.parent / "pit"
API = runpy.run_path(str(PIT))
AT = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def event(kind, at=AT, **fields):
    return {"kind": kind, "ts": at.strftime("%Y-%m-%dT%H:%M:%SZ"), **fields}


def lap(lid, seconds, at=AT, **fields):
    return [event("lap_start", at - timedelta(seconds=seconds), lap=lid,
                  project="demo", title=f"Title {lid}", **fields),
            event("lap_ship", at, lap=lid)]


def ask(aid, at=AT, **fields):
    return event("ask", at, id=aid, type="context", agent="codex", project="demo",
                 headline=aid, **fields)


def state(events, at=AT):
    return API["build_state"](API["build_model"](events), at)


def score_row(day, **scores):
    return {"date": day, **dict.fromkeys(API["SCORE_KEYS"]), **scores}


class RaceProjection(unittest.TestCase):
    def test_empty_and_legacy_identity_are_explicitly_null(self):
        empty = state([])
        self.assertEqual(empty["event_count"], 0)
        self.assertEqual(empty["drivers"], {})
        self.assertEqual(empty["laps"], {"running": [], "pace_hours": 4, "last": None,
                                        "finished": [], "last_hours": None,
                                        "best_hours": None, "shipped_total": 0})
        events = [ask("legacy"), ask("linked", lap="running"),
                  event("lap_start", lap="running", project="demo", title="Old lap"),
                  event("lap_start", lap="new", project="demo", title="New lap", agent="codex")]
        snapshot = state(events)
        self.assertEqual(snapshot["event_count"], len(events))
        self.assertEqual([a["lap"] for a in snapshot["open_asks"]], [None, "running"])
        self.assertEqual([l["agent"] for l in snapshot["laps"]["running"]], [None, "codex"])

    def test_pace_is_exact_first_ten_ever_and_stays_fixed(self):
        events = []
        for i, seconds in enumerate(range(3601, 3612)):
            events += lap(str(i), seconds, AT - timedelta(days=30, hours=-i))
            expected = 4 if i < 9 else 3605.5 / 3600
            self.assertEqual(state(events)["laps"]["pace_hours"], expected)
        events += lap("recent", 100000)
        self.assertEqual(state(events)["laps"]["pace_hours"], 3605.5 / 3600)
        self.assertEqual(state(events)["laps"]["last_hours"], 27.78)
        self.assertEqual(state(events)["laps"]["best_hours"], 1.0)

    def test_shipping_timestamp_ties_follow_ship_order_for_pace_and_scores(self):
        durations = [("last", 100)] + [(str(i), 10 if i < 5 else 1) for i in range(10)]
        events = [lap(lid, hours * 3600)[0] for lid, hours in durations]
        events += [event("lap_ship", lap=str(i)) for i in range(10)]
        events.append(event("lap_ship", lap="last"))
        laps = state(events)["laps"]
        self.assertEqual(laps["pace_hours"], 5.5)
        self.assertEqual(laps["last"]["lap"], "last")
        self.assertEqual([result["lap"] for result in laps["finished"]],
                         [str(i) for i in range(10)] + ["last"])
        self.assertEqual(API["calculate_scores"](events, AT)["shipping"], 28)

    def test_ratings_use_exact_durations_and_strict_pace(self):
        events = []
        expected = [(3600, "best"), (3601, "good"), (3600, "best"),
                    (3599, "best"), (14400, "slow"), (14399, "good")]
        for i, (seconds, rating) in enumerate(expected):
            events += lap(str(i), seconds, AT - timedelta(seconds=len(expected) - i), agent="codex")
            result = state(events)["laps"]["last"]
            self.assertEqual(result["rating"], rating)
            self.assertEqual(result["agent"], "codex")
        self.assertEqual(state(events)["laps"]["finished"][0]["hours"],
                         state(events)["laps"]["finished"][1]["hours"])
        self.assertEqual(set(result), {"lap", "project", "title", "agent", "hours", "shipped_at", "rating"})

    def test_tenth_rating_uses_new_baseline_and_history_does_not_change(self):
        durations = [3600] + [7200] * 8 + [10000, 7200, 7199]
        events = []
        ratings = []
        for i, seconds in enumerate(durations):
            events += lap(str(i), seconds, AT - timedelta(seconds=len(durations) - i))
            ratings.append(state(events)["laps"]["last"]["rating"])
        self.assertEqual(ratings[8:], ["good", "slow", "slow", "good"])
        self.assertEqual([r["rating"] for r in state(events)["laps"]["finished"]], ratings)

    def test_zero_baseline_is_preserved(self):
        events = [e for i in range(10) for e in lap(str(i), 0)]
        self.assertEqual(state(events)["laps"]["pace_hours"], 0)
        self.assertEqual(state(events)["laps"]["last"]["rating"], "best")

    def test_recent_finished_window_is_inclusive_and_excludes_future(self):
        events = lap("old", 3600, AT - timedelta(seconds=601))
        events += lap("edge", 3600, AT - timedelta(seconds=600))
        events += lap("new", 3600, AT - timedelta(seconds=1))
        events += lap("future", 3600, AT + timedelta(seconds=1))
        laps = state(events)["laps"]
        self.assertEqual([r["lap"] for r in laps["finished"]], ["edge", "new"])
        self.assertEqual(laps["last"]["lap"], "new")
        self.assertEqual(laps["shipped_total"], 3)
        self.assertIsNone(laps["last"]["agent"])


class PitStopProjection(unittest.TestCase):
    def test_no_answers_and_future_answers_are_absent(self):
        empty = {"fastest_today_minutes": None, "last_minutes": None}
        self.assertEqual(state([])["pit_stops"], empty)
        self.assertEqual(state([ask("open")])["pit_stops"], empty)
        events = [ask("future"), event("answer", AT + timedelta(seconds=1), id="future")]
        self.assertEqual(state(events)["pit_stops"], empty)

    def test_latest_answer_per_ask_original_wait_and_reopen(self):
        events = [ask("a", AT - timedelta(hours=1)),
                  event("answer", AT - timedelta(minutes=59), id="a"),
                  event("reopen", AT - timedelta(minutes=50), id="a"),
                  event("answer", AT - timedelta(minutes=30), id="a"),
                  event("reopen", AT - timedelta(minutes=20), id="a"),
                  ask("b", AT - timedelta(minutes=10)), event("answer", AT, id="b")]
        self.assertEqual(state(events)["pit_stops"], {"fastest_today_minutes": 10, "last_minutes": 10})
        self.assertEqual(state(events[:5])["pit_stops"], {"fastest_today_minutes": 30, "last_minutes": 30})
        events += [event("answer", AT + timedelta(days=1), id="a")]
        self.assertEqual(state(events)["pit_stops"]["fastest_today_minutes"], 10)
        self.assertEqual(state(events[:5] + events[-1:])["pit_stops"],
                         {"fastest_today_minutes": 30, "last_minutes": 30})

    def test_last_uses_timestamp_then_physical_answer_order(self):
        events = [ask("a", AT - timedelta(seconds=91)), ask("b", AT - timedelta(seconds=300)),
                  event("answer", AT, id="b"), event("answer", AT, id="a")]
        self.assertEqual(state(events)["pit_stops"], {"fastest_today_minutes": 91 / 60, "last_minutes": 91 / 60})
        events.append(event("answer", AT - timedelta(seconds=1), id="b"))
        self.assertEqual(state(events)["pit_stops"]["last_minutes"], 91 / 60)

    def test_local_midnight_uses_converted_answer_date(self):
        previous = os.environ.get("TZ")
        self.addCleanup(self.restore_timezone, previous)
        os.environ["TZ"] = "America/Los_Angeles"
        time.tzset()
        at = datetime(2026, 11, 17, 8, 1, tzinfo=timezone.utc)
        events = [ask("yesterday", at - timedelta(minutes=10)),
                  event("answer", at - timedelta(minutes=2), id="yesterday"),
                  ask("today", at - timedelta(minutes=5)), event("answer", at, id="today")]
        self.assertEqual(state(events, at)["pit_stops"], {"fastest_today_minutes": 5, "last_minutes": 5})
        before_midnight = at - timedelta(minutes=2)
        self.assertEqual(state(events, before_midnight)["pit_stops"],
                         {"fastest_today_minutes": 8, "last_minutes": 8})

    @staticmethod
    def restore_timezone(previous):
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


class ScoreTrends(unittest.TestCase):
    def trends(self, *values):
        rows = [score_row(f"2026-11-{i + 1:02d}", speed=value) for i, value in enumerate(values)]
        return API["calculate_scores_trend"](rows)["speed"]

    def test_all_comparisons_and_best_ties(self):
        for values, expected in (((80,), None), ((), None), ((80, 80), "best"),
                                 ((90, 40, 60), "up"), ((90, 60, 40), "down"),
                                 ((90, 40, 40), "flat"), ((90, 40, 90), "best"),
                                 ((None, 80), "best"), ((90, None, 80), None),
                                 ((80, None), None), ((None, None), None)):
            with self.subTest(values=values):
                self.assertEqual(self.trends(*values), expected)


class RaceCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = {**os.environ, "PITWALL_HOME": str(self.home)}

    def pit(self, *args):
        result = subprocess.run([str(PIT), *args], cwd=self.home, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def snapshot(self):
        return json.loads((self.home / "state.json").read_text())

    def write(self, name, value):
        (self.home / name).write_text(json.dumps(value))

    def test_agent_is_optional_and_persists_in_event_and_projection(self):
        self.pit("lap", "start", "--title", "Legacy invocation")
        self.pit("lap", "start", "--title", "New invocation", "--agent", "codex")
        events = [json.loads(line) for line in (self.home / "events.jsonl").read_text().splitlines()]
        self.assertEqual([e["agent"] for e in events], [None, "codex"])
        self.assertEqual([l["agent"] for l in self.snapshot()["laps"]["running"]], [None, "codex"])
        self.assertEqual(self.snapshot()["event_count"], 2)

    def test_valid_driver_mapping_is_projected_unchanged_and_npx_preserved(self):
        drivers = {"codex": {"program": "codex", "color": "#3b82f6", "tyre": "medium"},
                   "glm-flash": {"program": None, "color": "#22C55e", "tyre": "hard"}}
        config = {"npx": "/some/executable", "drivers": drivers}
        self.write("config.json", config)
        self.pit("state")
        self.assertEqual(self.snapshot()["drivers"], drivers)
        self.assertEqual(json.loads((self.home / "config.json").read_text()), config)
        self.write("config.json", {"npx": "/some/executable"})
        self.pit("state")
        self.assertEqual(self.snapshot()["drivers"], {})

    def test_bad_driver_sections_are_independent_and_keep_asks_and_scores(self):
        today = date.today().isoformat()
        row = score_row(today, speed=80)
        (self.home / "scores.jsonl").write_text(json.dumps(row) + "\n")
        base = {"program": "codex", "color": "#3b82f6", "tyre": "medium"}
        bad_configs = ["{bad", "[]", json.dumps({"drivers": []})]
        for key, bad in (("program", ""), ("program", 123), ("color", "red"),
                         ("color", "#abcdef00"), ("color", None), ("tyre", "rain")):
            bad_configs.append(json.dumps({"drivers": {"codex": {**base, key: bad}}}))
        for config in bad_configs:
            with self.subTest(config=config):
                (self.home / "config.json").write_text(config)
                result = self.pit("ask", "--type", "context", "--agent", "codex",
                                  "--headline", "Still responsive", "--reason", "test")
                self.assertIn("drivers unavailable", result.stderr)
                self.assertEqual(self.snapshot()["drivers"], {})
                self.assertEqual(self.snapshot()["scores"], {k: row[k] for k in API["SCORE_KEYS"]})
                self.assertTrue(self.snapshot()["open_asks"])

    def test_trends_use_sorted_distinct_dates_last_physical_row_and_exclude_future(self):
        today = date.today()
        rows = [score_row(str(today), speed=100),
                score_row(str(today - timedelta(days=2)), speed=90),
                score_row(str(today - timedelta(days=1)), speed=40),
                score_row(str(today), speed=60),
                score_row(str(today + timedelta(days=1)), speed=0)]
        (self.home / "scores.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.pit("state")
        self.assertEqual(self.snapshot()["scores"]["speed"], 60)
        self.assertEqual(self.snapshot()["scores_trend"]["speed"], "up")
        (self.home / "scores.jsonl").write_text(json.dumps(rows[0]) + "\n" + json.dumps(rows[3]) + "\n")
        self.pit("state")
        self.assertIsNone(self.snapshot()["scores_trend"]["speed"])


if __name__ == "__main__":
    unittest.main()
