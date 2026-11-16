# pitwall

Agents treat Chris as a tool with six typed asks. `pit` logs every ask, answer, lap and concept to one append-only file, and rebuilds a state file that the Herdr pit wall view reads.

## Files

| Path | What it holds |
|---|---|
| `pit` | The command. One Python 3 file, standard library only. Symlinked to `~/.local/bin/pit`. |
| `RULES.md` | The rules every agent follows. `~/.claude/CLAUDE.md` imports it with `@~/pitwall/RULES.md`, and `~/.codex/AGENTS.md` is a symlink to it. Edit it here and every harness sees the change. |
| `tests/test_pit.py` | Unit tests. Run `python3 -m unittest discover -s ~/pitwall/tests`. |

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
