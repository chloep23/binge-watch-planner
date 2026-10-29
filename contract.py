"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    READ_WATCHLIST = "read_watchlist"
    READ_FREE_TIME = "read_free_time"
    REPORT_SCHEDULE = "report_schedule"
    PLAN_WEEK = "plan_week"
    MERGE_FREE_TIME = "merge_free_time"
    TOTAL_RUNTIME = "total_runtime"


class Task(Enum):
    WEEK_PLAN = "week-plan"
    READ_WATCHLIST = "read-watchlist"


class Outcome(Enum):
    FINISHED = "finished"
    LEFT = "left"
    OUT_OF_TIME = "out-of-time"


WATCHLIST = "The watchlist file, relative to the workspace, e.g. watchlist.json"
FREE_TIME = "The free-time file, relative to the workspace, e.g. free_time.json"
STAMP = 'A local date and time "YYYY-MM-DD HH:MM", 24-hour, with no time zone, e.g. "2026-03-02 19:00"'
DAY = 'A local calendar day "YYYY-MM-DD"'
SHOW = "The show's title, exactly as the watchlist writes it"
RUN = "The run that read the files and saved the report, as the tools return it: copy it unchanged"
LEAVES = (
    "When the show leaves the platform, a local date and time; null when it never leaves. An episode "
    "may be watched only if it ends at or before this"
)
SOURCE_HASH = "sha256 over the watchlist and free-time files the plan was built from"
EPISODE_NUMBER = "The episode's number, as the watchlist gives it"


@dataclass
class Episode(Output):
    number: Annotated[int, EPISODE_NUMBER]
    minutes: Annotated[int, "How long the episode runs, in whole minutes"]


@dataclass
class Show(Output):
    title: Annotated[str, SHOW]
    leaves: Annotated[str | None, LEAVES]
    episodes: Annotated[list[Episode], "Its episodes, in the order they must be watched"]


@dataclass
class Watchlist(Output):
    shows: Annotated[list[Show], "The shows, in the order they must be watched"]


@dataclass
class Block(Output):
    start: Annotated[str, STAMP]
    end: Annotated[str, STAMP]


@dataclass
class Week(Output):
    first_day: Annotated[str, DAY]
    last_day: Annotated[str, DAY]
    blocks: Annotated[list[Block], "The free-time blocks, in order, never overlapping and never merged"]


@dataclass
class WatchlistInput(Output):
    watchlist: Annotated[str, WATCHLIST]


@dataclass
class WatchlistOutput(Output):
    watchlist: Annotated[Watchlist, "The watchlist as the file states it"]
    source_sha256: Annotated[str, "sha256 of the watchlist file"]


@dataclass
class SourceInput(Output):
    watchlist: Annotated[str, WATCHLIST]
    free_time: Annotated[str, FREE_TIME]


@dataclass
class FreeTimeOutput(Output):
    week: Annotated[Week, "The week and its blocks, as the file states them"]
    source_sha256: Annotated[str, "sha256 of the free-time file"]


@dataclass
class Watched(Output):
    show: Annotated[str, SHOW]
    episode: Annotated[int, EPISODE_NUMBER]
    end: Annotated[str, "When the episode ends, a local date and time; the day it falls on is the day it counts for"]


@dataclass
class DayPlan(Output):
    date: Annotated[str, DAY]
    episodes: Annotated[list[Watched], "The episodes ending that day, in the order they were watched; [] for none"]


@dataclass
class ShowOutcome(Output):
    show: Annotated[str, SHOW]
    outcome: Annotated[
        Outcome,
        "finished: every episode watched; left: the show left the platform with episodes unwatched; "
        "out-of-time: the week ran out with episodes unwatched",
    ]
    finished_at: Annotated[str | None, "When its last episode ended, or null when it was never finished"]
    unwatched: Annotated[list[int], "The episode numbers never watched, in order; [] when the show was finished"]


@dataclass
class ReportInput(Output):
    task: Annotated[SourceInput, "The task input, exactly as given"]
    days: Annotated[list[DayPlan], "The days this call reports; an earlier entry for the same day is replaced"]
    shows: Annotated[list[ShowOutcome], "The shows this call reports; an earlier entry for the same show is replaced"]


@dataclass
class WeekPlanOutput(Output):
    task: Annotated[SourceInput, "The task input, exactly as given"]
    run: Annotated[str, RUN]
    days: Annotated[list[DayPlan], "Every day of the week, in order, including the days nothing was watched"]
    shows: Annotated[list[ShowOutcome], "Every show in the watchlist, in its order"]


@dataclass
class ReportOutput(Output):
    path: Annotated[str, "The report file, relative to the workspace: reports/<run>/plan.json"]
    covered: Annotated[int, "How many of the week's days the merged report covers so far"]
    complete: Annotated[bool, "Whether every day and every show is covered: then submit the report"]
    report: Annotated[WeekPlanOutput, "The merged report so far"]


@dataclass
class KeyOutput(Output):
    source_sha256: Annotated[str, SOURCE_HASH]
    days: Annotated[list[DayPlan], "Every day of the week, in order"]
    shows: Annotated[list[ShowOutcome], "Every show in the watchlist, in its order"]


@dataclass
class MergedOutput(Output):
    blocks: Annotated[list[Block], "The blocks with every pair that touches or overlaps joined into one span"]
    merged: Annotated[int, "How many blocks were joined away"]


@dataclass
class ShowRuntime(Output):
    show: Annotated[str, SHOW]
    episodes: Annotated[int, "How many episodes the show has"]
    minutes: Annotated[int, "Their total runtime in minutes"]


@dataclass
class RuntimeOutput(Output):
    shows: Annotated[list[ShowRuntime], "Each show's episode count and total runtime, in watchlist order"]
    minutes: Annotated[int, "The whole watchlist's runtime in minutes"]
    free_minutes: Annotated[int, "The week's free time in minutes, counting every block"]


TOOLS = {
    Tool.READ_WATCHLIST: (WatchlistInput, WatchlistOutput),
    Tool.READ_FREE_TIME: (SourceInput, FreeTimeOutput),
    Tool.REPORT_SCHEDULE: (ReportInput, ReportOutput),
    Tool.PLAN_WEEK: (SourceInput, KeyOutput),
    Tool.MERGE_FREE_TIME: (SourceInput, MergedOutput),
    Tool.TOTAL_RUNTIME: (SourceInput, RuntimeOutput),
}
TASKS = {
    Task.WEEK_PLAN: (SourceInput, WeekPlanOutput),
    Task.READ_WATCHLIST: (WatchlistInput, WatchlistOutput),
}
