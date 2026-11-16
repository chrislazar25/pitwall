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
pit usage pull
pit ledger show
```

Bad input exits with code 2 and one line on stderr. A reopened ask goes back into the pit and can be answered again.

## Install the Herdr tower

With Herdr running, run:

```sh
python3 scripts/install_mod.py --dock
```

The installer checks the source before copying and checks the installed mod afterward. `--dock` creates a personal `pitwall` copy of Herdr's `main` layout and places the tower on the right at 380 px. The shipped layout stays intact. Add `--side left` to move the tower left. Omit `--dock` to update the mod without switching layouts.

The tower reads `~/.pitwall/state.json` and watches `~/.pitwall` for changes. A 30-second fallback refreshes the data and elapsed times. Missing or invalid state shows `NO DATA`. The mod never writes files or runs commands.

GRID shows Herdr's live agents. IN PIT shows open asks. SECTORS shows four scores, and LAPS shows running and completed lap times. FUEL shows usage and spend after collection. GARAGE and RADIO remain placeholders for Phase 4.

To check the behavior and native render, run:

```sh
python3 -m unittest discover -s tests
node --test tests/test_tower.mjs
python3 scripts/check_mod.py
```

The model tests use Node 22 or newer. Herdr runs the installed mod in its own native JavaScript environment. Phase screenshots stay local and are ignored by Git.

## Usage and spend

`pit usage pull` reads Claude Code and Codex usage through the verified per-tool `ccusage` commands. It stores the absolute path of `npx` in `~/.pitwall/config.json`, raw reports in `~/.pitwall/usage/raw-TOOL.json`, and normalized rows in `~/.pitwall/usage/daily.json`. Collection runs outside the event-log lock so agents can still ask questions during a refresh.

Normalized input includes cached input. The cache columns are subsets of input, so totals add only `input_tokens` and `output_tokens`.

| Normalized field | Observed ccusage source |
|---|---|
| `date` | Daily `date` |
| `model` | Claude `modelBreakdowns[].modelName`; Codex `models` key |
| `input_tokens` | `inputTokens + cacheCreationTokens + cacheReadTokens` |
| `output_tokens` | `outputTokens` |
| `cache_write_tokens` | `cacheCreationTokens` |
| `cache_read_tokens` | `cacheReadTokens` |
| `api_value_usd` | Claude model `cost`; Codex daily `costUSD` for its single model |

`cacheCreation1hTokens` and `reasoningOutputTokens` are already included in their parent counters. They are not added again. A report without a model breakdown uses `model: "all"`. A Codex day with several models and no per-model costs also uses one `all` row, preserving the exact daily cost without estimating a split.

Fuel uses the local calendar day. Seven-day totals include today and the previous six dates. Thirty-day value includes today and the previous 29 dates. Future rows are excluded. Later asks and answers rebuild fuel from the saved usage and ledger.

`~/.pitwall/ledger.json` holds user-supplied rows with `provider`, `plan`, `usd_per_month`, and `renews_on`. `pit ledger show` prints those rows and the monthly total. An empty ledger gives a null value ratio. Subscription charges stay separate from the API-equivalent value reported by ccusage.

The hourly cron command requires explicit approval before installation. Usage reports, the ledger, configuration, and cron logs stay outside the repository.
