"""The tools that read the files and plan the week: read_watchlist, read_free_time, plan_week,
and the two that answer a narrower question, merge_free_time and total_runtime.

``plan_week`` is the task's reference: it builds its answer with :func:`plugin.rules.plan`, the
one simulation, so the answer key can never drift from what the agent is shown.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from contract import (
    Block,
    DayPlan,
    FreeTimeOutput,
    KeyOutput,
    MergedOutput,
    RuntimeOutput,
    ShowOutcome,
    ShowRuntime,
    SourceInput,
    Watched,
    WatchlistInput,
    WatchlistOutput,
)
from plugin.clock import minutes_of, stamp_text
from plugin.rules import RuleError, load_sources, plan, read_text, read_watchlist_data, read_week_data, sha256_text

# One token per plugin process: every file a run writes lands under reports/<RUN>/.
RUN = secrets.token_hex(8)
REPORTS = "reports"
MARKER = "run.json"


def run_folder(workspace: Path, run: str = RUN) -> Path:
    """The run's folder, made with its marker the first time a tool writes."""
    folder = Path(workspace) / REPORTS / run
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / MARKER
    if not marker.is_file():
        marker.write_text(json.dumps({"run": run}), encoding="utf-8")
    return folder


def receipt(workspace: Path, name: str, body: dict) -> None:
    """What a read tool leaves behind, so the verdict can see the files were read in this run."""
    (run_folder(Path(workspace)) / name).write_text(json.dumps({"run": RUN, **body}, indent=1), encoding="utf-8")


def parsed(workspace: Path, name: str, reader):
    text = read_text(Path(workspace), name)
    try:
        return reader(json.loads(text)), sha256_text(text)
    except json.JSONDecodeError as error:
        raise RuleError(f"{name} is not JSON: {error}") from error


def read_watchlist(given: WatchlistInput, workspace: Path) -> WatchlistOutput:
    watchlist, digest = parsed(workspace, given.watchlist, read_watchlist_data)
    receipt(workspace, "watchlist.json", {"watchlist": given.watchlist, "sha256": digest})
    return WatchlistOutput(watchlist=watchlist, source_sha256=digest)


def read_free_time(given: SourceInput, workspace: Path) -> FreeTimeOutput:
    week, digest = parsed(workspace, given.free_time, read_week_data)
    receipt(workspace, "free_time.json", {"free_time": given.free_time, "sha256": digest})
    return FreeTimeOutput(week=week, source_sha256=digest)


def planned(given: SourceInput, workspace: Path):
    watchlist, week, source = load_sources(Path(workspace), given.watchlist, given.free_time)
    return plan(watchlist, week), source


def plan_week(given: SourceInput, workspace: Path) -> KeyOutput:
    made, source = planned(given, workspace)
    days = [
        DayPlan(
            date=day,
            episodes=[Watched(show=watch.show, episode=watch.episode, end=stamp_text(watch.end)) for watch in watches],
        )
        for day, watches in made.days
    ]
    shows = [
        ShowOutcome(show=title, outcome=outcome, finished_at=None if at is None else stamp_text(at), unwatched=unwatched)
        for title, outcome, at, unwatched in made.shows
    ]
    return KeyOutput(source_sha256=source, days=days, shows=shows)


def merge_free_time(given: SourceInput, workspace: Path) -> MergedOutput:
    _, week, _ = load_sources(Path(workspace), given.watchlist, given.free_time)
    spans: list[list[int]] = []
    for block in week.blocks:
        start, end = minutes_of(block.start, "start"), minutes_of(block.end, "end")
        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    blocks = [Block(start=stamp_text(start), end=stamp_text(end)) for start, end in spans]
    return MergedOutput(blocks=blocks, merged=len(week.blocks) - len(blocks))


def total_runtime(given: SourceInput, workspace: Path) -> RuntimeOutput:
    watchlist, week, _ = load_sources(Path(workspace), given.watchlist, given.free_time)
    shows = [
        ShowRuntime(show=show.title, episodes=len(show.episodes), minutes=sum(item.minutes for item in show.episodes))
        for show in watchlist.shows
    ]
    free = sum(minutes_of(block.end, "end") - minutes_of(block.start, "start") for block in week.blocks)
    return RuntimeOutput(shows=shows, minutes=sum(entry.minutes for entry in shows), free_minutes=free)
