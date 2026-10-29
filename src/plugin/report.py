"""report_schedule: merge this run's days and show outcomes into its report file."""

from __future__ import annotations

import json
from pathlib import Path

from contract import DayPlan, ReportInput, ReportOutput, ShowOutcome, Watched, WeekPlanOutput
from plugin.clock import day_minutes, days_between
from plugin.rules import RuleError, load_sources
from plugin.watching import REPORTS, RUN, run_folder

REPORT = "plan.json"


def report_path(run: str = RUN) -> str:
    return f"{REPORTS}/{run}/{REPORT}"


def report_schedule(given: ReportInput, workspace: Path) -> ReportOutput:
    watchlist, week, _ = load_sources(Path(workspace), given.task.watchlist, given.task.free_time)
    days = days_between(day_minutes(week.first_day, "first_day"), day_minutes(week.last_day, "last_day"))
    titles = [show.title for show in watchlist.shows]
    for name, named, known in (("day", [entry.date for entry in given.days], days), ("show", [entry.show for entry in given.shows], titles)):
        unknown = [value for value in named if value not in known]
        if unknown:
            raise RuleError(f"{unknown[0]!r} is not a {name} of this week" if name == "day" else f"the watchlist has no show {unknown[0]!r}")
        if len(set(named)) != len(named):
            raise RuleError(f"a {name} is named twice in one call")

    folder = run_folder(Path(workspace))
    path = folder / REPORT
    held = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"days": {}, "shows": {}}
    wanted = {"watchlist": given.task.watchlist, "free_time": given.task.free_time}
    if held.get("task") not in (None, wanted):
        raise RuleError(f"{report_path()} is another task's report: start a new run")
    for entry in given.days:
        held["days"][entry.date] = [{"show": watch.show, "episode": watch.episode, "end": watch.end} for watch in entry.episodes]
    for entry in given.shows:
        held["shows"][entry.show] = {
            "outcome": entry.outcome.value,
            "finished_at": entry.finished_at,
            "unwatched": list(entry.unwatched),
        }
    held["task"] = wanted
    path.write_text(json.dumps(held, indent=1), encoding="utf-8")

    made_days = [
        DayPlan(date=day, episodes=[Watched(**watch) for watch in held["days"][day]]) for day in days if day in held["days"]
    ]
    made_shows = [
        ShowOutcome(show=title, outcome=held["shows"][title]["outcome"], finished_at=held["shows"][title]["finished_at"], unwatched=held["shows"][title]["unwatched"])
        for title in titles
        if title in held["shows"]
    ]
    complete = len(made_days) == len(days) and len(made_shows) == len(titles)
    report = WeekPlanOutput(task=given.task, run=RUN, days=made_days, shows=made_shows)
    return ReportOutput(path=report_path(), covered=len(made_days), complete=complete, report=report)
