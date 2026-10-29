"""Staging a workspace and running the prescribed path, as the host runs a week-plan task."""

from __future__ import annotations

import shutil
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
from contract import KeyOutput, ReportInput, SourceInput, WeekPlanOutput
from plugin import plan_week, read_free_time, read_watchlist, report_schedule

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WATCHLIST = "watchlist.json"
FREE_TIME = "free_time.json"
# The schedule the rules give for the main fixtures, worked out by hand from the README's rules.
DAYS = {
    "2026-03-02": [("Glass Harbour", 1, "2026-03-02 19:45")],  # episode 1 fills the block exactly
    "2026-03-03": [
        ("Glass Harbour", 2, "2026-03-03 21:00"),  # ends exactly at the leaving time
        ("The Ninth Kitchen", 1, "2026-03-03 21:30"),  # the next show starts in the same block
        ("The Ninth Kitchen", 2, "2026-03-03 22:00"),
    ],
    "2026-03-04": [],  # the block starting 23:00 has nothing ending before midnight
    "2026-03-05": [
        ("The Ninth Kitchen", 3, "2026-03-05 00:00"),  # ends exactly at midnight: the new day
        ("Saltmarsh", 1, "2026-03-05 00:25"),  # just after midnight
    ],
    "2026-03-06": [],  # two touching blocks, neither long enough: they never merge
    "2026-03-07": [("Saltmarsh", 2, "2026-03-07 10:50")],
    "2026-03-08": [],  # the watchlist was finished before the week ended
}
SHOWS = [
    ("Glass Harbour", "left", None, [3, 4]),
    ("The Ninth Kitchen", "finished", "2026-03-05 00:00", []),
    ("Saltmarsh", "finished", "2026-03-07 10:50", []),
]


def stage(workspace: Path, *names: str) -> None:
    """Copy fixture files into the workspace, as a run stages its task's inputs."""
    workspace.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy(FIXTURES / name, workspace / name)


class Run:
    """One task's workspace: the staged inputs, the tools, and the verdict on what was submitted."""

    def __init__(self, workspace: Path, watchlist: str = WATCHLIST, free_time: str = FREE_TIME) -> None:
        self.workspace = workspace
        self.task = {"watchlist": watchlist, "free_time": free_time}
        stage(workspace, watchlist, free_time)
        self.given = build_output(self.task, SourceInput)
        self.submitted: dict | None = None
        # The host pins the reference before the agent runs.
        self.key: KeyOutput = build_output(plain_output(plan_week(self.given, workspace)), KeyOutput)

    def read(self):
        """The two read calls of the prescribed path, which leave this run's receipts."""
        from contract import WatchlistInput

        read_watchlist(build_output({"watchlist": self.task["watchlist"]}, WatchlistInput), self.workspace)
        return read_free_time(self.given, self.workspace)

    def report(self, days: list[dict], shows: list[dict]) -> dict:
        given = build_output({"task": self.task, "days": days, "shows": shows}, ReportInput)
        self.submitted = plain_output(report_schedule(given, self.workspace).report)
        return self.submitted

    def answer(self) -> tuple[list[dict], list[dict]]:
        """The answer key, in the shape report_schedule takes."""
        days = [
            {"date": day.date, "episodes": [{"show": w.show, "episode": w.episode, "end": w.end} for w in day.episodes]}
            for day in self.key.days
        ]
        shows = [
            {"show": s.show, "outcome": s.outcome.value, "finished_at": s.finished_at, "unwatched": list(s.unwatched)}
            for s in self.key.shows
        ]
        return days, shows

    def gold(self) -> dict:
        """The prescribed path, reported right: read both files, then one report call."""
        self.read()
        return self.report(*self.answer())

    def verdict(self, report: dict | None = None, reference: KeyOutput | None = ...) -> dict:
        found = report if report is not None else self.submitted
        return verifier.verify_task(
            "week-plan",
            self.given,
            build_output(found, WeekPlanOutput),
            self.key if reference is ... else reference,
            str(self.workspace),
        )


def failed(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["constraints"] if entry["ok"] is False]


def unchecked(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["constraints"] if entry["ok"] is None]
