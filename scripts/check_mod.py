#!/usr/bin/env python3
"""Check the native Pit tower with snapshots produced by the Pit CLI."""

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[1]
    source = repo / "mods/pitwall"
    herdr = shutil.which("herdr-app") or str(Path.home() / ".local/bin/herdr-app")
    subprocess.run([herdr, "check", str(source)], check=True)
    with tempfile.TemporaryDirectory(prefix="pitwall-check-") as scratch:
        root = Path(scratch)
        env = {**os.environ, "PITWALL_HOME": str(root / "data")}

        def pit(*args):
            return subprocess.run([str(repo / "pit"), *args], cwd=repo, env=env,
                                  check=True, capture_output=True, text=True).stdout

        empty = json.loads(pit("state"))
        pit("ask", "--type", "taste", "--agent", "codex", "--headline",
            "Dock this timing tower on the right or left?", "--reason", "Native render check",
            "--option", "right", "--option", "left", "--default", "right")
        pit("lap", "start", "--title", "Pit wall build")
        loaded = json.loads(pit("state"))
        loaded["scores"] = {"speed": 100, "ask_quality": 0, "shipping": 52.5, "ownership": None}
        loaded["laps"]["last_hours"] = 1.25
        loaded["laps"]["best_hours"] = 0.5
        overdue = copy.deepcopy(loaded)
        overdue["open_asks"][0]["asked_at"] = "2000-01-01T00:00:00Z"
        overdue["open_asks"][0]["headline"] = "A long headline that must stay on one line " * 12
        fixtures = {
            "missing": None,
            "malformed": "{",
            "wrong-shape": "{}",
            "empty": json.dumps(empty),
            "loaded": json.dumps(loaded),
            "overdue-long": json.dumps(overdue),
        }
        for name, text in fixtures.items():
            folder = root / name
            shutil.copytree(source, folder, ignore=shutil.ignore_patterns(
                "*.d.ts", "jsconfig.json", "*.error"))
            (folder / "main.js").rename(folder / "tower.js")
            (folder / "main.js").write_text(
                'import Tower from "./tower.js";\n'
                'export default class extends Tower {\n'
                f'  init() {{ this.snapshotText = {json.dumps(text)}; }}\n'
                '}\n'
            )
            print(f"Native fixture: {name}", flush=True)
            subprocess.run([herdr, "check", str(folder)], check=True)


if __name__ == "__main__":
    main()
