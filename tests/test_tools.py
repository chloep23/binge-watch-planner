"""The tools as the agent and the host call them: what they return, what they write, and that
each one raises rather than returning a made-up value."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import DAYS, FREE_TIME, WATCHLIST, Run, stage
from slimconfig import build_output

from contract import ReportInput, SourceInput, WatchlistInput
from plugin import merge_free_time, plan_week, read_free_time, read_watchlist, report_schedule, total_runtime
from plugin.rules import RuleError
from plugin.watching import RUN


def test_read_watchlist_states_the_file_and_leaves_a_receipt(tmp_path: Path) -> None:
    stage(tmp_path, WATCHLIST)
    found = read_watchlist(build_output({"watchlist": WATCHLIST}, WatchlistInput), tmp_path)
    assert [show.title for show in found.watchlist.shows] == ["Glass Harbour", "The Ninth Kitchen", "Saltmarsh"]
    assert found.watchlist.shows[0].leaves == "2026-03-03 21:00"
    receipt = json.loads((tmp_path / "reports" / RUN / "watchlist.json").read_text())
    assert receipt == {"run": RUN, "watchlist": WATCHLIST, "sha256": found.source_sha256}


def test_read_free_time_states_the_week(tmp_path: Path) -> None:
    run = Run(tmp_path)
    found = read_free_time(run.given, tmp_path)
    assert (found.week.first_day, found.week.last_day) == ("2026-03-02", "2026-03-08")
    assert len(found.week.blocks) == 8
    assert json.loads((tmp_path / "reports" / RUN / "free_time.json").read_text())["free_time"] == FREE_TIME


def test_plan_week_matches_the_hand_derived_schedule(tmp_path: Path) -> None:
    run = Run(tmp_path)
    key = run.key
    assert {d.date: [(w.show, w.episode, w.end) for w in d.episodes] for d in key.days} == DAYS


def test_report_schedule_merges_two_calls_and_reports_completeness(tmp_path: Path) -> None:
    run = Run(tmp_path)
    run.read()
    days, shows = run.answer()
    first = report_schedule(build_output({"task": run.task, "days": days[:4], "shows": []}, ReportInput), tmp_path)
    assert first.covered == 4 and first.complete is False
    second = report_schedule(build_output({"task": run.task, "days": days[4:], "shows": shows}, ReportInput), tmp_path)
    assert second.covered == 7 and second.complete is True
    assert [entry.date for entry in second.report.days] == sorted(DAYS), "the week's order, not the calls'"


def test_merge_free_time_joins_only_what_touches(tmp_path: Path) -> None:
    run = Run(tmp_path)
    found = merge_free_time(run.given, tmp_path)
    assert found.merged == 2, "03-03 21:00 and 03-06 19:40 each join a pair"
    assert ("2026-03-06 19:00", "2026-03-06 20:20") in [(b.start, b.end) for b in found.blocks]


def test_total_runtime_counts_the_watchlist_and_the_week(tmp_path: Path) -> None:
    run = Run(tmp_path)
    found = total_runtime(run.given, tmp_path)
    assert [(s.show, s.episodes, s.minutes) for s in found.shows] == [
        ("Glass Harbour", 4, 195),
        ("The Ninth Kitchen", 3, 120),
        ("Saltmarsh", 2, 75),
    ]
    assert found.minutes == 390
    assert found.free_minutes == 45 + 59 + 60 + 60 + 100 + 40 + 40 + 60


def test_the_week_has_more_free_time_than_the_watchlist_needs_and_still_does_not_finish(tmp_path: Path) -> None:
    """Why total_runtime does not answer the task: 464 free minutes against 390 of episodes, and
    Glass Harbour still leaves with two episodes unwatched."""
    run = Run(tmp_path)
    totals = total_runtime(run.given, tmp_path)
    assert totals.free_minutes > totals.minutes
    assert next(s for s in run.key.shows if s.show == "Glass Harbour").unwatched == [3, 4]


def test_every_tool_raises_rather_than_returning_a_partial_value(tmp_path: Path) -> None:
    stage(tmp_path, WATCHLIST, FREE_TIME)
    missing = build_output({"watchlist": WATCHLIST, "free_time": "nothing.json"}, SourceInput)
    for tool in (read_free_time, plan_week, merge_free_time, total_runtime):
        with pytest.raises(RuleError, match="no file at"):
            tool(missing, tmp_path)
    with pytest.raises(RuleError, match="inside the workspace"):
        read_watchlist(build_output({"watchlist": "../escape.json"}, WatchlistInput), tmp_path)
    run = Run(tmp_path)
    unknown = {"task": run.task, "days": [], "shows": [{"show": "Nope", "outcome": "finished", "finished_at": None, "unwatched": []}]}
    with pytest.raises(RuleError, match="no show"):
        report_schedule(build_output(unknown, ReportInput), tmp_path)
    bad_day = {"task": run.task, "days": [{"date": "2026-04-01", "episodes": []}], "shows": []}
    with pytest.raises(RuleError, match="not a day of this week"):
        report_schedule(build_output(bad_day, ReportInput), tmp_path)
