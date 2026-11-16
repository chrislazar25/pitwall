#!/usr/bin/env python3
"""Install the race prototype without switching layouts or changing existing layouts."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    app_home = Path(os.environ.get("HERDR_APP_HOME", Path.home() / ".config/herdr-app"))
    herdr = shutil.which("herdr-app") or str(Path.home() / ".local/bin/herdr-app")
    source = root / "mods/racetrack"
    layout = root / "layouts/race.json"
    destination = app_home / "layouts/race.json"
    if destination.exists() and json.loads(destination.read_text()) != json.loads(layout.read_text()):
        raise SystemExit("race.json already exists with different content; preserve it before installing")
    subprocess.run([herdr, "check", str(source)], check=True)
    target = app_home / "mods/racetrack"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".race-install-", dir=app_home) as scratch:
        staged = Path(scratch)
        for file in source.iterdir():
            if file.suffix not in (".js", ".svg", ".json") or file.name == "jsconfig.json":
                continue
            shutil.copyfile(file, staged / file.name)
        for file in sorted(staged.iterdir(), key=lambda p: p.name == "main.js"):
            os.replace(file, target / file.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(layout, staged / "race.json")
        os.replace(staged / "race.json", destination)
    subprocess.run([herdr, "check", str(target)], check=True)
    print(f"Installed {target} and {destination}")


if __name__ == "__main__":
    main()
