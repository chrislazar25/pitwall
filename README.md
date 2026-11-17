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
pit lap start --title TEXT [--agent NAME]
pit lap ship ID
pit concept add NAME [--must-own] | must-own NAME | pass NAME | override NAME --reason TEXT | list
pit open
pit state
pit usage pull
pit ledger show
pit score
pit health
pit coach
```

Bad input exits with code 2 and one line on stderr. A reopened ask goes back into the pit and can be answered again.

## Install the Herdr tower

With Herdr running, run:

```sh
python3 scripts/install_mod.py --dock
```

The installer checks the source before copying and checks the installed mod afterward. `--dock` creates a personal `pitwall` copy of Herdr's `main` layout and places the tower on the right at 380 px. The shipped layout stays intact. Add `--side left` to move the tower left. Omit `--dock` to update the mod without switching layouts.

The tower reads `~/.pitwall/state.json` and watches `~/.pitwall` for changes. A 30-second fallback refreshes the data and elapsed times. Missing or invalid state shows `NO DATA`. The mod never writes files or runs commands.

GRID shows Herdr's live agents. IN PIT shows open asks. SECTORS shows four scores, and LAPS shows running and completed lap times. FUEL shows usage and spend after collection. GARAGE shows registered project checks. RADIO shows the latest accepted coach note.

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

## Scores, project health, and coach

`pit score` calculates four separate scores from the event log and appends a dated record to `~/.pitwall/scores.jsonl`. A later record for the same date replaces that date's earlier value when the history is read.

| Score | Calculation |
|---|---|
| SPEED | `100 × (120 − median wait minutes) ÷ 115`, limited to 0–100 |
| ASKS | Percent of answered asks marked needed and never reopened |
| SHIP | `50 × baseline median lap hours ÷ current median lap hours`, capped at 100 |
| OWN | Percent of current must-own concepts marked passed |

The ask cohort contains unique asks answered in the last seven times 24 hours. A repeated answer uses the latest answer in that window, measured from the original ask. Reopened asks remain in the cohort but lose quality credit. Shipping compares the first ten shipped laps with shipments in the seven-day window. Ownership uses the current concept state, including earlier passes and explicit overrides. Future events are excluded. Scores are rounded half-up after calculation.

Unavailable metrics show dashes. Shipping needs ten shipped laps and at least one recent shipment. A zero current median with a positive baseline scores 100; two zero medians are undefined and show a dash. Ownership needs at least one must-own concept. Only the user marks concepts must-own.

`pit health` checks every existing registered project and saves `~/.pitwall/garage.json`. Its flags mean the following:

| Flag | Evidence |
|---|---|
| CI | A YAML workflow file directly under `.github/workflows/` |
| TEST | A root `tests`, `test`, or `__tests__` directory |
| README | A root file whose name starts with `README` |
| ACTIVE | A commit within the previous 14 days |
| 7D | Git's commit count since seven days ago |

These flags describe repository files and activity. They do not claim that CI or tests passed. Deleted project paths are omitted. A directory without a usable Git HEAD has inactive status and zero commits.

`pit coach` sends the current state, the previous 14 days of events, and 14 calendar days of usage to the installed headless Claude CLI. The coach runs with customizations, hooks, built-in tools, and MCP tools disabled. It can produce text but cannot execute commands or edit code or rules.

The reply must contain exactly two nonempty lines, beginning `Observation: ` and `Tweak: `. With less than seven days of event history, the observation must say `not enough data yet`. Accepted replies become `~/.pitwall/coach/YYYY-MM-DD.md`. Invalid replies go to `.rejected.md` and leave the accepted note intact. The coach proposes changes; it does not apply them.

The coach skips a run when the latest seven distinct score dates all have four scores of at least 60 and the newest accepted note is less than 14 calendar days old. Dates need not be consecutive. Rejected notes do not affect this check.

Scores, garage data, and accepted notes survive later asks and state rebuilds. Slow Git and Claude processes run outside the event-log lock. A damaged optional analytics file produces a diagnostic without preventing an ask from being logged.

The daily 08:23 local-time score, health, and coach job requires explicit approval before installation. It preserves the existing hourly usage job. The full track-and-pit visual theme is a separate proposed pass.

## Race layout

Chris accepted the circuit in Phase 5 Step A. Install the live race view with
`python3 scripts/install_mod.py` and `python3 scripts/install_race.py`, then run
`herdr-app do layout.switch '{"name":"race"}'`. The new layout shows laps above
the focused agent's real terminal, with the Pit tower in a right drawer.
Existing layouts and keys are preserved. The race installer recognizes the
accepted prototype but refuses to overwrite custom layout changes.

Start attributed work with `pit lap start --agent codex --title "short title"`.
Driver entries in `~/.pitwall/config.json` map Pit names to observed Herdr
program keys, colors, and tyres. Claude uses `claude` and Codex uses `codex`.
GLM has not been observed, so its program stays null and it has no terminal link.
Existing laps without an agent remain visible and unlinked.

Car position is elapsed time divided by shipping pace. It is a clock, not task
progress. Pace is the median of the first ten shipped laps, or four hours until
then. Open asks place matching cars in the pit. Clicking a linked car or garage
icon focuses its real terminal. The latest ten-minute finishes remain visible.
The flag bar prioritizes overdue asks, no working agents, recent finishes, then
green. Its pit-stop times use the latest answer per ask, dated locally today.

The tower owns ask sounds and the Dock badge. It requires Herdr's `checking()`
and `setBadge()` APIs and suppresses both effects if either is unavailable.
The first valid load establishes a silent baseline. Later new ask IDs play one
blocked sound per load. Duplicate tower copies coordinate through shared state;
stale event snapshots cannot replay notifications. An invalid read preserves the
previous notification baseline and badge.

The initial installed Herdr 0.1.15 lacks those two APIs. Herdr's cached 0.1.16
release notes advertise them. Sound, Dock badge, and the user acceptance checks
remain pending until the host supports them. See [PHASE5.md](PHASE5.md) for the
complete behavior and acceptance requirements.
