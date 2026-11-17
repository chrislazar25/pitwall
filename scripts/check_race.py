#!/usr/bin/env python3
"""Check the native circuit with disposable snapshots produced by the Pit CLI."""

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from herdr_check import native_check


def main():
    repo = Path(__file__).resolve().parents[1]
    source = repo / "mods/racetrack"
    herdr = shutil.which("herdr-app") or str(Path.home() / ".local/bin/herdr-app")
    native_check(herdr, source)
    with tempfile.TemporaryDirectory(prefix="race-check-") as scratch:
        root = Path(scratch)
        data = root / "data"
        data.mkdir()
        (data / "config.json").write_text(json.dumps({"drivers": {
            "codex": {"program": "codex", "color": "#3b82f6", "tyre": "medium"},
            "claude": {"program": "claude", "color": "#e8743b", "tyre": "soft"},
        }}))
        env = {**os.environ, "PITWALL_HOME": str(data)}

        def pit(*args):
            return subprocess.run([str(repo / "pit"), *args], cwd=repo, env=env,
                                  check=True, capture_output=True, text=True).stdout.strip()

        empty = pit("state")
        lap = pit("lap", "start", "--agent", "codex", "--title", "Native race check")
        running = json.loads(pit("state"))
        ask = pit("ask", "--type", "context", "--agent", "codex", "--lap", lap,
                  "--headline", "Native pit fixture", "--reason", "Disposable render check")
        waiting = pit("state")
        pit("answer", ask, "--answer", "Fixture accepted", "--took-default", "na")
        pit("lap", "ship", lap)
        finished = pit("state")
        for i in range(8):
            pit("lap", "start", "--agent", "claude", "--title", f"Waiting lap {i + 1}")
        pit("ask", "--type", "context", "--agent", "claude", "--headline", "Eight waiting laps",
            "--reason", "Exercise shared pit boxes")
        overflow = pit("state")
        overtime = copy.deepcopy(running)
        overtime["laps"]["running"][0]["started_at"] = "2000-01-01T00:00:00Z"
        zero_pace = copy.deepcopy(running)
        zero_pace["laps"]["pace_hours"] = 0
        fixtures = {"missing": None, "malformed": "{", "wrong-shape": "{}",
                    "empty": empty, "track": json.dumps(running), "pit": waiting,
                    "finished": finished, "overflow": overflow,
                    "overtime": json.dumps(overtime), "zero-pace": json.dumps(zero_pace)}
        for name, text in fixtures.items():
            folder = root / name
            shutil.copytree(source, folder, ignore=shutil.ignore_patterns(
                "*.d.ts", "jsconfig.json", "*.error"))
            (folder / "main.js").rename(folder / "circuit.js")
            (folder / "main.js").write_text(
                'import Circuit from "./circuit.js";\n'
                'export default class extends Circuit {\n'
                f'  init() {{ this.snapshotText = {json.dumps(text)}; '
                'this.size = {width: 1000, height: 500}; }\n'
                '}\n')
            print(f"Native fixture: {name}", flush=True)
            native_check(herdr, folder)
        print(f"OK: source and {len(fixtures)} native race fixtures", flush=True)


if __name__ == "__main__":
    main()
