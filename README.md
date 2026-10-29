# Binge Watch Planner

A `nanoagent.plugin/v0001` plugin that works out which episodes of a watchlist get
finished on each day of a week of free time, and checks the answer with a deterministic
verifier. No network: everything is read from files in the workspace.

## Tools

| Name | Kind | Does | Code |
|---|---|---|---|
| `read_watchlist` | tool | Reads a watchlist: shows in order, episode runtimes, leaving times | `src/plugin/watching.py` |
| `read_free_time` | tool | Reads a free-time file: the week and its blocks, checked in order and non-overlapping | `src/plugin/watching.py` |
| `report_schedule` | tool | Merges the days and show outcomes it is given into this run's report | `src/plugin/report.py` |
| `plan_week` | tool | Works the whole week out end to end | `src/plugin/watching.py` |
| `merge_free_time` | tool | Joins every pair of blocks that touches into one span | `src/plugin/watching.py` |
| `total_runtime` | tool | Each show's episode count and runtime, the watchlist's total, the week's free minutes | `src/plugin/watching.py` |
| `week-plan` | task | Reports each day's finished episodes and each show's outcome: runner `agent`, reference `plan_week` | `verifier/task.py` |
| `read-watchlist` | task | States a watchlist's shows, episodes and leaving times: runner `tool` | `verifier/watchlist.py` |

`merge_free_time` and `total_runtime` are honest about what they do and are not how this
task is solved. Merged blocks are **not** the blocks you watch in — rule 3 below — and free
time adding up to more than the watchlist's runtime does not mean the watchlist gets
finished, because rule 2 wastes whatever is left at the end of a block.

## The rules

Times are local, written `YYYY-MM-DD HH:MM`, with no time zones. Days are `YYYY-MM-DD`.

A watchlist and a free-time file are JSON:

```json
{"shows": [
  {"title": "Glass Harbour", "leaves": "2026-03-03 21:00",
   "episodes": [{"number": 1, "minutes": 45}, {"number": 2, "minutes": 60}]}
]}
```

```json
{"first_day": "2026-03-02", "last_day": "2026-03-08",
 "blocks": [{"start": "2026-03-02 19:00", "end": "2026-03-02 19:45"}]}
```

`leaves` may be `null` for a show that never leaves. Blocks are in order, never overlap, and
every one runs inside `first_day 00:00` to `last_day 23:59`.

1. **Order.** Shows are watched in watchlist order and episodes in theirs. A show is
   finished, or has left, before the next one starts. Never skip ahead to a shorter episode
   or a later show, even when one would fit and the current episode would not.
2. **Fitting.** An episode must fit entirely inside one block. If the next episode does not
   fit in the time left, the rest of that block is wasted.
3. **Blocks never merge**, even back to back: a block ending at 20:00 and one starting at
   20:00 are separate, and an episode longer than either alone cannot be watched across
   them.
4. **Leaving.** An episode can be watched only if it ends at or before its show's leaving
   time; ending exactly at that time is allowed. Once a show has left, its unwatched
   episodes are reported as unfinished, and watching moves on to the next show, within the
   same block if time remains.
5. **Days.** An episode is credited to the day on which it ends, and **midnight opens a
   day**: an episode ending at `00:00` counts for the new day, as does one ending at
   `00:20`.

A show ends the week as `finished` (every episode watched, with the time its last one
ended), `left` (it left the platform with episodes unwatched) or `out-of-time` (the week
ran out with episodes unwatched).

## The verdict

`verify_task` decides a `week-plan` submission on 12 constraints, in order. A failure among
the first 9 scores 0; past them the score is the share of the week's days and the
watchlist's shows that are exactly right.

| # | Constraint | Holds when |
|---|---|---|
| 1 | `answer-key` | The answer key planned this task's files |
| 2 | `sources` | The watchlist and the free-time file are well formed |
| 3 | `answer-key-right` | The answer key follows the watching rules |
| 4 | `this-run` | The report names a run of this workspace |
| 5 | `read-sources` | read_watchlist and read_free_time read this task's files in this run |
| 6 | `report-saved` | report_schedule saved this run's report for this task |
| 7 | `submitted-task` | The submitted report is for this task |
| 8 | `submitted-shape` | The submitted report is well formed |
| 9 | `submitted-as-saved` | The submitted report equals the saved report |
| 10 | `all-days` | Every day of the week is reported exactly once, in order |
| 11 | `episodes-exact` | Each day lists exactly the episodes ending that day, in the order watched |
| 12 | `shows-exact` | Each show's outcome, finishing time and unwatched episodes are right |

The verifier never runs a model. It reads the two files itself in `verifier/rules.py`,
which shares no code with the plugin, and keeps time in `verifier/civil.py`, which is
integer arithmetic only: a verifier may not import `datetime`, so the calendar is the
days-from-civil algorithm, checked against the standard library's on thousands of dates.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # environment variable NAMEs this plugin needs, never values
├── src/plugin/      # the MCP server: __main__.py, its IMPLEMENTATIONS, and the plugin's own modules
├── tests/           # the suite, with its invented watchlists and weeks under fixtures/
├── ui/              # how the page draws the outputs: renderers.js and renderers.css
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package
```

`contract.py` is the one place a value's shape is declared. Its `Output` classes are the
JSON Schemas the server offers and the agent sees, and every input and output is built into
its class on the way in and out. A tool that fails raises; NanoAgent sees an MCP error.

Every show in `tests/fixtures/` is invented, and the week is built so that each rule has a
case that turns on it: an episode that exactly fills a block, one a minute too long, two
touching blocks that do not merge, a show leaving at a block boundary with the next show
taking the rest, an episode ending exactly at a leaving time, one ending exactly at
midnight and one just after, a week where nothing fits, and a watchlist finished with days
to spare.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

Publishing checks every plugin rule: push the plugin to a public GitHub repository
and submit its URL on RUSH Lab.
