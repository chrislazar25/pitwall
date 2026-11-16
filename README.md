# pitwall

Agents treat Chris as a tool with six typed asks. `pit` logs every ask, answer, lap and concept to one append-only file, and rebuilds a state file that the Herdr pit wall view reads.

## Files

| Path | What it holds |
|---|---|
| `pit` | The command. One Python 3 file, standard library only. Symlinked to `~/.local/bin/pit`. |
| `RULES.md` | The rules every agent follows. `~/.claude/CLAUDE.md` imports it with `@~/pitwall/RULES.md`, and `~/.codex/AGENTS.md` is a symlink to it. Edit it here and every harness sees the change. |
| `tests/test_pit.py` | Unit tests. Run `python3 -m unittest discover -s ~/pitwall/tests`. |
| `mods/pitwall/` | Native Herdr timing tower. Reads Pit state and the live agent list. |
| `scripts/install_mod.py` | Checks and installs the tower into Herdr. |

Data lives in `~/.pitwall/` (or `$PITWALL_HOME`). `events.jsonl` is the log and is never edited in place. `state.json` is rebuilt from it after every write, and `projects.json` maps each project name to its repo path. Answered decisions also go to `.pit/decisions.md` in each project's repo.

## Commands

```
pit ask --type decide|review|unblock|taste|context|teach --agent A --headline H --reason R
        [--option O ...] [--default D] [--artifact X] [--lap L] [--concept C]
pit answer ID --answer TEXT --took-default yes|no|na [--not-needed]
pit reopen ID
pit control --action pause|cancel|reprioritize|revoke --agent A [--note TEXT]
pit lap start --title TEXT
pit lap ship ID
pit concept add NAME [--must-own] | must-own NAME | pass NAME | override NAME --reason TEXT | list
pit open
pit state
```

Bad input exits with code 2 and one line on stderr. A reopened ask goes back into the pit and can be answered again.

## Install the Herdr tower

With Herdr running, run:

```sh
python3 scripts/install_mod.py --dock
```

The installer checks the source before copying and checks the installed mod afterward. `--dock` creates a personal `pitwall` copy of Herdr's `main` layout and places the tower on the right at 380 px. The shipped layout stays intact. Add `--side left` to move the tower left. Omit `--dock` to update the mod without switching layouts.

The tower reads `~/.pitwall/state.json` and watches `~/.pitwall` for changes. A 30-second fallback refreshes the data and elapsed times. Missing or invalid state shows `NO DATA`. The mod never writes files or runs commands.

GRID shows Herdr's live agents. IN PIT shows open asks. SECTORS shows four scores, and LAPS shows running and completed lap times. FUEL, GARAGE, and RADIO remain placeholders for later phases.

To check the behavior and native render, run:

```sh
python3 -m unittest discover -s tests
node --test tests/test_tower.mjs
python3 scripts/check_mod.py
```

The model tests use Node 22 or newer. Herdr runs the installed mod in its own native JavaScript environment. Phase screenshots stay local and are ignored by Git.
