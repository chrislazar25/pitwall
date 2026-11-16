import copy
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path

PIT = Path(__file__).resolve().parent.parent / "pit"
FIXTURES = Path(__file__).parent / "fixtures"
api = runpy.run_path(str(PIT))
map_usage = api["map_usage"]
calculate_fuel = api["calculate_fuel"]
BadInput = api["BadInput"]


def report(tool):
    return json.loads((FIXTURES / f"ccusage-{tool}.json").read_text())


class Mapping(unittest.TestCase):
    def test_real_claude_cache_creation_1h_is_already_in_cache_total(self):
        self.assertEqual(map_usage("claude", report("claude")), [{
            "date": "2026-11-16", "tool": "claude", "model": "claude-opus-5-5",
            "input_tokens": 14346185, "output_tokens": 80904,
            "cache_write_tokens": 457710, "cache_read_tokens": 13888283,
            "api_value_usd": 8.0581846}])

    def test_real_codex_cost_is_attributed_to_its_only_model_without_double_reasoning(self):
        self.assertEqual(map_usage("codex", report("codex")), [{
            "date": "2026-11-16", "tool": "codex", "model": "gpt-6.1-sol",
            "input_tokens": 21158610, "output_tokens": 54119,
            "cache_write_tokens": 0, "cache_read_tokens": 20737408,
            "api_value_usd": 3.4573348}])

    def test_absent_model_breakdown_uses_all(self):
        for tool, key in (("claude", "modelBreakdowns"), ("codex", "models")):
            raw = report(tool)
            del raw["daily"][0][key]
            rows = map_usage(tool, raw)
            self.assertEqual(rows[0]["model"], "all")
            self.assertEqual(rows[0]["input_tokens"] + rows[0]["output_tokens"],
                             raw["daily"][0]["totalTokens"])

    def test_codex_multiple_models_without_costs_preserves_whole_day(self):
        raw = report("codex")
        raw["daily"][0]["models"]["another-model"] = copy.deepcopy(
            raw["daily"][0]["models"]["gpt-6.1-sol"])
        rows = map_usage("codex", raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["model"], "all")
        self.assertEqual(rows[0]["api_value_usd"], 3.4573348)
        self.assertEqual(rows[0]["input_tokens"] + rows[0]["output_tokens"], 21212729)

    def test_day_token_and_split_cost_mismatch_are_errors(self):
        for tool in ("claude", "codex"):
            raw = report(tool)
            raw["daily"][0]["totalTokens"] += 1
            with self.assertRaises(BadInput):
                map_usage(tool, raw)
        raw = report("claude")
        raw["daily"][0]["modelBreakdowns"][0]["cost"] += 1
        with self.assertRaises(BadInput):
            map_usage("claude", raw)

    def test_malformed_reports_do_not_become_empty_data(self):
        for raw in ({}, {"daily": None}, {"daily": [None]}):
            with self.assertRaises(BadInput):
                map_usage("claude", raw)
        raw = report("codex")
        raw["daily"][0]["date"] = "2026-02-30"
        with self.assertRaises(BadInput):
            map_usage("codex", raw)

    def test_calendar_boundaries_future_exclusion_and_cache_subsets(self):
        today = date(2026, 11, 16)
        rows = []
        for age, tool, tokens, cost in ((0, "codex", 10, 1), (6, "claude", 20, 2),
                                       (7, "codex", 30, 3), (29, "codex", 40, 4),
                                       (30, "claude", 50, 5), (-1, "codex", 60, 6)):
            rows.append({"date": (today - timedelta(days=age)).isoformat(), "tool": tool,
                         "model": "all", "input_tokens": tokens - 1, "output_tokens": 1,
                         "cache_write_tokens": 2, "cache_read_tokens": 3, "api_value_usd": cost})
        fuel = calculate_fuel(rows, [{"usd_per_month": 5}, {"usd_per_month": 15}], today)
        self.assertEqual(fuel, {"tokens_today": 10, "tokens_7d": 30,
                               "by_tool_7d": [{"tool": "claude", "tokens": 20},
                                              {"tool": "codex", "tokens": 10}],
                               "api_value_30d_usd": 10, "out_of_pocket_month_usd": 20,
                               "value_ratio": .5})
        self.assertIsNone(calculate_fuel(rows, [], today)["value_ratio"])
        self.assertEqual(calculate_fuel([], [], today), {
            "tokens_today": 0, "tokens_7d": 0, "by_tool_7d": [],
            "api_value_30d_usd": 0, "out_of_pocket_month_usd": 0, "value_ratio": None})


class UsageCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "pitwall"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "PITWALL_HOME": str(self.home),
                    "CLAUDE_CONFIG_DIR": str(self.root / "claude"),
                    "CODEX_HOME": str(self.root / "codex"),
                    "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", "")}
        for tool in ("claude", "codex"):
            raw = report(tool)
            raw["daily"][0]["date"] = date.today().isoformat()
            (self.root / f"{tool}.json").write_text(json.dumps(raw))
        self.fake = self.bin / "npx"
        self.fake.write_text(f'''#!{sys.executable}
import json, pathlib, sys, time
root = pathlib.Path({str(self.root)!r})
with (root / "argv.jsonl").open("a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if (root / "block").exists():
    (root / "started").touch()
    while not (root / "release").exists():
        time.sleep(.02)
if (root / "fail").exists():
    print("report command failed", file=sys.stderr)
    sys.exit(9)
print((root / (sys.argv[3] + ".json")).read_text())
''')
        self.fake.chmod(0o755)

    def pit(self, *args, timeout=10):
        return subprocess.run([str(PIT), *args], cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=timeout)

    def ok(self, *args):
        result = self.pit(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def read(self, name):
        return json.loads((self.home / name).read_text())

    def ledger(self):
        return [{"provider": "example", "plan": "user plan", "usd_per_month": 20,
                 "renews_on": "2026-12-01"}]

    def test_pull_saves_exact_raw_reports_rows_config_and_fuel_survives_event(self):
        (self.home / "config.json").write_text(json.dumps({"unrelated": {"keep": True}}))
        ledger = json.dumps(self.ledger())
        (self.home / "ledger.json").write_text(ledger)
        self.ok("usage", "pull")
        self.assertEqual(self.read("config.json"), {"unrelated": {"keep": True}, "npx": str(self.fake)})
        self.assertEqual((self.home / "ledger.json").read_text(), ledger)
        calls = [json.loads(line) for line in (self.root / "argv.jsonl").read_text().splitlines()]
        self.assertEqual(calls, [["--yes", "ccusage@latest", tool, "daily", "--json"]
                                 for tool in ("claude", "codex")])
        for tool in ("claude", "codex"):
            self.assertEqual(self.read(f"usage/raw-{tool}.json"),
                             json.loads((self.root / f"{tool}.json").read_text()))
        rows = self.read("usage/daily.json")
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["input_tokens"] + row["output_tokens"] for row in rows), 35639818)
        fuel = self.read("state.json")["fuel"]
        self.assertEqual(fuel["tokens_today"], 35639818)
        self.assertEqual(fuel["tokens_7d"], 35639818)
        self.assertAlmostEqual(fuel["api_value_30d_usd"], 11.5155194)
        self.assertEqual(fuel["out_of_pocket_month_usd"], 20)
        self.assertAlmostEqual(fuel["value_ratio"], .57577597)
        result = self.ok("ask", "--type", "context", "--agent", "test", "--headline", "question",
                         "--reason", "need fact")
        state = self.read("state.json")
        self.assertEqual(state["fuel"], fuel)
        self.assertEqual(state["open_asks"][0]["id"], result.stdout.strip())
        output = self.ok("ledger", "show").stdout
        self.assertIn("example\tuser plan\t$20.00/mo\t2026-12-01", output)
        self.assertIn("TOTAL $20.00/mo", output)

    def test_failures_preserve_previous_publication(self):
        self.ok("usage", "pull")
        names = ["usage/raw-claude.json", "usage/raw-codex.json", "usage/daily.json", "state.json"]
        before = {name: (self.home / name).read_bytes() for name in names}
        for failure in ("subprocess", "json", "invariant", "ledger"):
            with self.subTest(failure=failure):
                raw = json.loads((self.root / "codex.json").read_text())
                if failure == "subprocess":
                    (self.root / "fail").touch()
                elif failure == "json":
                    (self.root / "codex.json").write_text("broken")
                elif failure == "invariant":
                    raw["daily"][0]["totalTokens"] += 1
                    (self.root / "codex.json").write_text(json.dumps(raw))
                else:
                    (self.home / "ledger.json").write_text('[{"usd_per_month": "unknown"}]')
                result = self.pit("usage", "pull")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
                self.assertEqual({name: (self.home / name).read_bytes() for name in names}, before)
                (self.root / "fail").unlink(missing_ok=True)
                raw = report("codex")
                raw["daily"][0]["date"] = date.today().isoformat()
                (self.root / "codex.json").write_text(json.dumps(raw))
                (self.home / "ledger.json").write_text("[]")

    def test_empty_harnesses_skip_once_and_successful_empty_is_zero(self):
        (self.root / "claude.json").write_text('{"daily": []}')
        (self.root / "codex.json").write_text('{"daily": []}')
        result = self.ok("usage", "pull")
        self.assertEqual(result.stderr.splitlines(), ["pit: claude: no data, skipped",
                                                     "pit: codex: no data, skipped"])
        self.assertEqual(self.read("usage/raw-claude.json"), {"daily": []})
        self.assertEqual(self.read("usage/raw-codex.json"), {"daily": []})
        self.assertEqual(self.read("usage/daily.json"), [])
        self.assertEqual(self.read("state.json")["fuel"]["tokens_today"], 0)
        self.assertEqual(self.read("ledger.json"), [])

    def test_ccusage_owns_custom_log_discovery_and_empty_reports_replace_old_raw(self):
        self.env["CLAUDE_CONFIG_DIR"] = str(self.root / "first") + "," + str(self.root / "second")
        self.env["CODEX_HOME"] = str(self.root / "custom-codex")
        self.ok("usage", "pull")
        self.assertEqual(self.read("state.json")["fuel"]["tokens_today"], 35639818)
        (self.root / "claude.json").write_text('{"daily": []}')
        self.ok("usage", "pull")
        self.assertEqual(self.read("usage/raw-claude.json"), {"daily": []})
        self.assertEqual(self.read("state.json")["fuel"]["tokens_today"], 21212729)

    def test_publication_filesystem_error_has_one_diagnostic(self):
        (self.home / "usage").write_text("blocked")
        result = self.pit("usage", "pull")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_successful_pull_repairs_corrupted_derived_daily(self):
        self.ok("usage", "pull")
        (self.home / "usage/daily.json").write_text("broken")
        self.ok("usage", "pull")
        self.assertEqual(len(self.read("usage/daily.json")), 2)
        self.assertEqual(self.read("state.json")["fuel"]["tokens_today"], 35639818)

    def test_multi_model_fallback_warns_once(self):
        raw = json.loads((self.root / "codex.json").read_text())
        raw["daily"][0]["models"]["other"] = copy.deepcopy(raw["daily"][0]["models"]["gpt-6.1-sol"])
        (self.root / "codex.json").write_text(json.dumps(raw))
        result = self.ok("usage", "pull")
        self.assertEqual(result.stderr.splitlines(),
                         ["pit: codex: multiple models without costs, aggregated as all"])
        self.assertEqual(self.read("usage/daily.json")[1]["model"], "all")

    def test_ledger_show_is_read_only_and_rejects_malformed_data(self):
        self.assertIn("TOTAL $0.00/mo", self.ok("ledger", "show").stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        for value in ("null", "{}", '[{"provider":"p","plan":"x","renews_on":"soon","usd_per_month":NaN}]'):
            (self.home / "ledger.json").write_text(value)
            result = self.pit("ledger", "show")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual((self.home / "ledger.json").read_text(), value)

    def test_event_survives_malformed_analytics_and_fuel_degrades(self):
        self.ok("usage", "pull")
        for name in ("ledger.json", "usage/daily.json"):
            original = (self.home / name).read_text()
            (self.home / name).write_text("invalid")
            result = self.ok("ask", "--type", "context", "--agent", name, "--headline", "question",
                             "--reason", "need fact")
            self.assertIn("fuel unavailable", result.stderr)
            state = self.read("state.json")
            self.assertIsNone(state["fuel"])
            self.assertIn(result.stdout.strip(), [ask["id"] for ask in state["open_asks"]])
            (self.home / name).write_text(original)

    def test_before_collection_fuel_is_null(self):
        self.assertIsNone(json.loads(self.ok("state").stdout)["fuel"])

    def test_blocked_npx_allows_ask_and_publication_folds_current_event(self):
        (self.root / "block").touch()
        process = subprocess.Popen([str(PIT), "usage", "pull"], cwd=self.root, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "started").exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.root / "started").exists())
            result = self.pit("ask", "--type", "context", "--agent", "test", "--headline", "concurrent",
                              "--reason", "need fact", timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(process.poll())
            ask_id = result.stdout.strip()
            (self.root / "release").touch()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
            state = self.read("state.json")
            self.assertEqual([ask["id"] for ask in state["open_asks"]], [ask_id])
            self.assertEqual(state["fuel"]["tokens_today"], 35639818)
        finally:
            (self.root / "release").touch()
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
