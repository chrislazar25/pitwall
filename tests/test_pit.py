import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PIT = Path(__file__).resolve().parent.parent / "pit"


class PitCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.repo = Path(tempfile.mkdtemp()) / "demo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        self.env = {**os.environ, "PITWALL_HOME": str(self.home)}

    def pit(self, *args, cwd=None):
        return subprocess.run([str(PIT), *args], cwd=cwd or self.repo, env=self.env,
                              capture_output=True, text=True)

    def ok(self, *args, **kw):
        r = self.pit(*args, **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def refused(self, *args):
        r = self.pit(*args)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        return r.stderr

    def state(self):
        return json.loads((self.home / "state.json").read_text())

    def events(self):
        return [json.loads(l) for l in (self.home / "events.jsonl").read_text().splitlines()]

    def ask(self, type_, *extra, agent="claude"):
        return self.ok("ask", "--type", type_, "--agent", agent, "--headline", f"h {type_}",
                       "--reason", "r", *extra)


class AskRules(PitCase):
    TWO = ("--option", "narrow", "--option", "wait")

    def test_decide_and_taste_need_two_options_and_a_default(self):
        for t in ("decide", "taste"):
            self.refused("ask", "--type", t, "--agent", "a", "--headline", "h", "--reason", "r",
                         "--option", "one", "--default", "one")
            self.refused("ask", "--type", t, "--agent", "a", "--headline", "h", "--reason", "r",
                         *self.TWO)
            self.assertRegex(self.ask(t, *self.TWO, "--default", "narrow", agent=t), r"^a-[0-9a-f]{8}$")

    def test_context_unblock_teach_refuse_a_default(self):
        for t in ("context", "unblock", "teach"):
            self.refused("ask", "--type", t, "--agent", "a", "--headline", "h", "--reason", "r",
                         "--concept", "c", "--default", "x")
        self.ask("context", agent="x")
        self.ask("unblock", agent="y")

    def test_teach_needs_a_concept(self):
        self.refused("ask", "--type", "teach", "--agent", "a", "--headline", "h", "--reason", "r")
        self.ask("teach", "--concept", "idempotency")

    def test_review_takes_options_or_none(self):
        self.ask("review", "--artifact", "pit@abc123")

    def test_unknown_type_refused(self):
        self.refused("ask", "--type", "vibe", "--agent", "a", "--headline", "h", "--reason", "r")

    def test_second_open_ask_warns_and_still_records(self):
        self.ask("context")
        r = self.pit("ask", "--type", "context", "--agent", "claude", "--headline", "again",
                     "--reason", "r")
        self.assertEqual(r.returncode, 0)
        self.assertIn("already has an open ask in demo", r.stderr)
        self.assertEqual(len(self.state()["open_asks"]), 2)

    def test_ask_records_project_and_registers_it(self):
        self.ask("context")
        self.assertEqual(self.events()[0]["project"], "demo")
        projects = json.loads((self.home / "projects.json").read_text())
        self.assertEqual(Path(projects["demo"]).resolve(), self.repo.resolve())

    def test_outside_a_repo_the_project_is_none(self):
        outside = tempfile.mkdtemp()
        self.ok("ask", "--type", "context", "--agent", "a", "--headline", "h", "--reason", "r",
                cwd=outside)
        self.assertEqual(self.events()[0]["project"], "none")


class Answers(PitCase):
    def test_answer_writes_decision_line_and_second_answer_is_refused(self):
        aid = self.ask("decide", "--option", "narrow", "--option", "wait", "--default", "narrow")
        self.ok("answer", aid, "--answer", "narrow", "--took-default", "yes")
        lines = (self.repo / ".pit" / "decisions.md").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^- \d{4}-\d{2}-\d{2} \[decide\] h decide -> narrow$")
        self.refused("answer", aid, "--answer", "wait", "--took-default", "no")

    def test_answer_records_needed_and_took_default(self):
        aid = self.ask("context")
        self.ok("answer", aid, "--answer", "yes, mine only", "--took-default", "na", "--not-needed")
        e = self.events()[-1]
        self.assertEqual((e["kind"], e["took_default"], e["needed"]), ("answer", "na", False))

    def test_unblock_and_teach_write_no_decision_line(self):
        for t, extra in (("unblock", ()), ("teach", ("--concept", "c"))):
            aid = self.ask(t, *extra, agent=t)
            self.ok("answer", aid, "--answer", "done", "--took-default", "na")
        self.assertFalse((self.repo / ".pit" / "decisions.md").exists())

    def test_unknown_id_refused(self):
        self.refused("answer", "a-00000000", "--answer", "x", "--took-default", "na")

    def test_bad_took_default_refused(self):
        aid = self.ask("context")
        self.refused("answer", aid, "--answer", "x", "--took-default", "maybe")


class Reopen(PitCase):
    def test_reopen_puts_an_answered_ask_back_in_the_pit(self):
        aid = self.ask("context")
        self.refused("reopen", aid)
        self.ok("answer", aid, "--answer", "x", "--took-default", "na")
        self.ok("reopen", aid)
        self.assertEqual([a["id"] for a in self.state()["open_asks"]], [aid])
        e = self.events()[-1]
        self.assertEqual((e["kind"], e["id"]), ("reopen", aid))
        self.ok("answer", aid, "--answer", "y", "--took-default", "na")
        self.assertEqual(self.state()["open_asks"], [])


class Laps(PitCase):
    def test_lap_start_and_ship(self):
        lid = self.ok("lap", "start", "--title", "Retry queue")
        self.assertRegex(lid, r"^l-[0-9a-f]{8}$")
        running = self.state()["laps"]["running"]
        self.assertEqual([(l["lap"], l["title"], l["project"]) for l in running],
                         [(lid, "Retry queue", "demo")])
        self.ok("lap", "ship", lid)
        laps = self.state()["laps"]
        self.assertEqual((laps["running"], laps["shipped_total"]), ([], 1))
        self.assertIsInstance(laps["last_hours"], float)
        self.assertEqual(laps["best_hours"], laps["last_hours"])
        self.refused("lap", "ship", lid)
        self.refused("lap", "ship", "l-00000000")


class Concepts(PitCase):
    def test_latest_concept_event_wins(self):
        self.ok("concept", "add", "idempotency")
        self.assertEqual(self.ok("concept", "list"), "idempotency\tmust-own=no\tnot_passed")
        self.ok("concept", "must-own", "idempotency")
        self.ok("concept", "pass", "idempotency")
        self.assertEqual(self.ok("concept", "list"), "idempotency\tmust-own=yes\tpassed")
        self.ok("concept", "add", "idempotency", "--must-own")
        self.assertEqual(self.ok("concept", "list"), "idempotency\tmust-own=yes\tnot_passed")

    def test_override_passes_with_reason(self):
        self.ok("concept", "add", "retries", "--must-own")
        self.ok("concept", "override", "retries", "--reason", "already know it")
        e = self.events()[-1]
        self.assertEqual((e["status"], e["note"], e["must_own"]), ("passed", "already know it", True))

    def test_unknown_concept_refused(self):
        self.refused("concept", "pass", "ghost")

    def test_list_shows_only_the_current_project(self):
        other = Path(tempfile.mkdtemp()) / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=other, check=True)
        self.ok("concept", "add", "elsewhere", cwd=other)
        self.ok("concept", "add", "here")
        self.assertEqual(self.ok("concept", "list"), "here\tmust-own=no\tnot_passed")


class State(PitCase):
    KEYS = {"generated_at", "open_asks", "laps", "scores", "fuel", "garage", "radio"}

    def test_state_is_rebuilt_after_each_write(self):
        aid = self.ask("context")
        s = self.state()
        self.assertEqual(set(s), self.KEYS)
        self.assertEqual([a["id"] for a in s["open_asks"]], [aid])
        self.ok("answer", aid, "--answer", "x", "--took-default", "na")
        self.assertEqual(self.state()["open_asks"], [])
        self.ok("lap", "start", "--title", "t")
        self.assertEqual(len(self.state()["laps"]["running"]), 1)

    def test_empty_state_has_every_key(self):
        s = json.loads(self.ok("state"))
        self.assertEqual(set(s), self.KEYS)
        self.assertEqual(s["scores"], {"speed": None, "ask_quality": None,
                                       "shipping": None, "ownership": None})
        self.assertEqual(s["laps"], {"running": [], "last_hours": None,
                                     "best_hours": None, "shipped_total": 0})

    def test_open_lists_waiting_minutes(self):
        self.ask("context")
        cols = self.ok("open").split("\t")
        self.assertEqual(cols[1:5], ["context", "claude", "demo", "0m"])

    def test_control_is_logged(self):
        self.ok("control", "--action", "pause", "--agent", "codex", "--note", "lunch")
        e = self.events()[-1]
        self.assertEqual((e["kind"], e["action"], e["agent"], e["project"]),
                         ("control", "pause", "codex", "demo"))
        self.refused("control", "--action", "explode", "--agent", "codex")


if __name__ == "__main__":
    unittest.main()
