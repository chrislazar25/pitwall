#!/usr/bin/env python3
"""Install the Pit tower into Herdr after its native check passes."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from herdr_check import native_check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-home", type=Path,
                        default=Path(os.environ.get("HERDR_APP_HOME", Path.home() / ".config/herdr-app")))
    parser.add_argument("--dock", action="store_true",
                        help="dock in a personal copy of Herdr's main layout")
    parser.add_argument("--side", choices=("right", "left"), default="right")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "mods/pitwall"
    herdr = shutil.which("herdr-app") or str(Path.home() / ".local/bin/herdr-app")
    native_check(herdr, source)
    target = args.app_home / "mods/pitwall"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pitwall-install-", dir=args.app_home) as scratch:
        staged = Path(scratch) / "pitwall"
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns(
            "*.d.ts", "jsconfig.json", "*.error"))
        if target.exists():
            for file in sorted(staged.iterdir(), key=lambda p: p.name == "main.js"):
                os.replace(file, target / file.name)
        else:
            staged.rename(target)
    native_check(herdr, target)
    print(f"Installed {target}")
    if args.dock:
        env = {**os.environ, "HERDR_APP_HOME": str(args.app_home)}
        layout_file = args.app_home / "layouts/pitwall.json"
        if not layout_file.exists():
            subprocess.run([herdr, "do", "layout.clone", json.dumps({"name": "main", "as": "pitwall"})],
                           env=env, check=True)
        layout = json.loads(layout_file.read_text())
        if layout.get("type") != "row":
            parser.error("the personal pitwall layout must have a row at its root")
        children = layout["children"]
        block = next((child for child in children if child.get("id") == "pitwall"), {
            "id": "pitwall", "type": "block", "size": {"px": 380}, "min": 300,
            "content": {"mod": "pitwall"},
        })
        children[:] = [child for child in children if child.get("id") != "pitwall"]
        children.insert(len(children) if args.side == "right" else 0, block)
        with tempfile.NamedTemporaryFile(mode="w", dir=layout_file.parent, delete=False) as staged:
            staged.write(json.dumps(layout, indent=2) + "\n")
        os.replace(staged.name, layout_file)
        subprocess.run([herdr, "do", "layout.switch", json.dumps({"name": "pitwall"})],
                       env=env, check=True)
        print(f"Docked {args.side} in the personal pitwall layout")


if __name__ == "__main__":
    main()
