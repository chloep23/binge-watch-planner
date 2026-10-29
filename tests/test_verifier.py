"""The week-plan verdict: a gold run holds every constraint, and each one fails on its own case
with its own message; plus the per-call checks and the read-watchlist task's verdict.

The cases are the five a verifier has to decide -- correct, wrong, missing, malformed, and the
boundaries where the watching rules part company with a reasonable guess.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from helpers import DAYS, SHOWS, WATCHLIST, Run, failed, stage
from slimconfig import build_output, plain_output

import verifier
from contract import KeyOutput, MergedOutput, ReportInput, WatchlistInput, WatchlistOutput
from plugin import merge_free_time, read_watchlist, total_runtime
from plugin.watching import RUN
from verifier.task import TEXT

CONSTRAINTS = len(TEXT)
PAIRS = [(WATCHLIST, "free_time.json"), ("watchlist_tiny.json", "free_time_tiny.json"), ("watchlist_early.json", "free_time_early.json")]


# ----- Correct -----


@pytest.mark.parametrize(("watchlist", "free_time"), PAIRS, ids=["main", "nothing-fits", "leaves-early"])
def test_a_gold_run_holds_every_constraint(tmp_path: Path, watchlist: str, free_time: str) -> None:
    run = Run(tmp_path, watchlist=watchlist, free_time=free_time)
    run.gold()
    found = run.verdict()
    assert found["valid"], found["message"]
    assert found["score"] == 1.0 and found["message"].startswith(f"All {CONSTRAINTS} checks hold")
    assert [entry["ok"] for entry in found["details"]["constraints"]] == [True] * CONSTRAINTS
    assert len(json.dumps(found)) < 8000, "the verdict lands in the chat's context: keep it small"


def test_the_gold_plan_is_the_hand_derived_schedule(tmp_path: Path) -> None:
    """The fixture's schedule is worked out by hand from the rules, not from the plugin."""
    report = Run(tmp_path).gold()
    days = {entry["date"]: [(w["show"], w["episode"], w["end"]) for w in entry["episodes"]] for entry in report["days"]}
    assert days == DAYS
    assert [(s["show"], s["outcome"], s["finished_at"], s["unwatched"]) for s in report["shows"]] == SHOWS


# ----- Wrong -----


def test_a_missing_episode_on_a_day_fails_episodes_exact(tmp_path: Path) -> None:
    run = Run(tmp_path)
    run.read()
    days, shows = run.answer()
    days[1]["episodes"] = days[1]["episodes"][1:]  # drop Glass Harbour 2 from 2026-03-03
    run.report(days, shows)
    found = run.verdict()
    assert failed(found) == ["episodes-exact"]
    assert "2026-03-03 is wrong: Glass Harbour 2 ends at 2026-03-03 21:00 that day and is not reported" in found["message"]
    assert found["score"] == pytest.approx(9 / 10)


def test_an_invented_episode_fails_episodes_exact(tmp_path: Path) -> None:
    run = Run(tmp_path)
    run.read()
    days, shows = run.answer()
    days[2]["episodes"] = [{"show": "Glass Harbour", "episode": 3, "end": "2026-03-04 23:50"}]
    run.report(days, shows)
    found = run.verdict()
    assert "episodes-exact" in failed(found)
    assert "is reported ending at 2026-03-04 23:50, which the rules do not give" in found["message"]


def test_a_wrong_show_outcome_fails_shows_exact(tmp_path: Path) -> None:
    run = Run(tmp_path)
    run.read()
    days, shows = run.answer()
    shows[0] = {**shows[0], "outcome": "out-of-time"}
    run.report(days, shows)
    found = run.verdict()
    assert failed(found) == ["shows-exact"]
    assert "Glass Harbour is wrong: it reads out-of-time" in found["message"] and "the rules give left" in found["message"]


def test_trusting_the_merged_blocks_gives_a_specific_wrong_day(tmp_path: Path) -> None:
    """merge_free_time is right about merging and wrong for this task: the two blocks on 2026-03-06
    touch, and Saltmarsh 2 fits the merged span but neither real block (rule 3)."""
    run = Run(tmp_path)
    merged = merge_free_time(run.given, tmp_path)
    span = next(block for block in merged.blocks if block.start == "2026-03-06 19:00")
    assert (span.start, span.end) == ("2026-03-06 19:00", "2026-03-06 20:20"), "80 minutes once merged"
    run.read()
    days, shows = run.answer()
    by_day = {entry["date"]: entry for entry in days}
    by_day["2026-03-06"]["episodes"] = [{"show": "Saltmarsh", "episode": 2, "end": "2026-03-06 19:50"}]
    by_day["2026-03-07"]["episodes"] = []
    shows[2] = {**shows[2], "finished_at": "2026-03-06 19:50"}
    run.report(days, shows)
    found = run.verdict()
    assert "episodes-exact" in failed(found)
    assert "2026-03-06 is wrong" in found["message"] and found["score"] < 1


def test_a_submission_that_is_not_the_saved_report_fails_submitted_as_saved(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    changed = copy.deepcopy(report)
    changed["days"][0]["episodes"] = []
    found = run.verdict(changed)
    assert failed(found)[0] == "submitted-as-saved" and found["score"] == 0.0


def test_an_answer_key_that_breaks_the_rules_fails_answer_key_right(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    key = plain_output(run.key)
    key["shows"][0] = {**key["shows"][0], "outcome": "out-of-time"}
    found = run.verdict(report, reference=build_output(key, KeyOutput))
    assert failed(found)[0] == "answer-key-right" and found["score"] == 0.0


# ----- Missing -----


def test_no_answer_key_fails_first_and_scores_zero(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    found = run.verdict(report, reference=None)
    assert failed(found)[0] == "answer-key" and found["score"] == 0.0 and "plan_week never read" in found["message"]


@pytest.mark.parametrize("receipt", ["watchlist.json", "free_time.json"])
def test_a_plan_without_reading_the_files_fails_read_sources(tmp_path: Path, receipt: str) -> None:
    run = Run(tmp_path)
    run.gold()
    (tmp_path / "reports" / RUN / receipt).unlink()
    found = run.verdict()
    assert failed(found)[0] == "read-sources" and found["score"] == 0.0
    assert "was never called in run" in found["message"]
    assert found["details"]["right"] == 10, "the plan is still judged, and still right"


def test_a_missing_day_fails_all_days(tmp_path: Path) -> None:
    run = Run(tmp_path)
    run.read()
    days, shows = run.answer()
    run.report([entry for entry in days if entry["date"] != "2026-03-08"], shows)
    found = run.verdict()
    assert failed(found) == ["all-days"]
    assert "1 of the 7 days is not reported (2026-03-08)" in found["message"]
    assert found["score"] == pytest.approx(9 / 10)


def test_no_saved_report_fails_report_saved(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    (tmp_path / "reports" / RUN / "plan.json").unlink()
    found = run.verdict(report)
    assert failed(found)[0] == "report-saved" and found["score"] == 0.0


def test_a_missing_source_file_fails_sources(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    (tmp_path / "free_time.json").unlink()
    found = run.verdict(report)
    assert "sources" in failed(found) and "No file at free_time.json" in found["message"]


# ----- Malformed -----


def test_an_episode_credited_to_the_wrong_day_fails_submitted_shape(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    broken = copy.deepcopy(report)
    broken["days"][0]["episodes"][0]["end"] = "2026-03-03 19:45"
    found = run.verdict(broken)
    assert failed(found) == ["submitted-shape"] and found["score"] == 0.0
    assert "which is not 2026-03-02: an episode counts for the day it ends on" in found["message"]


@pytest.mark.parametrize(
    ("end", "words"),
    [("2026-03-02 24:00", "must be a time"), ("2026-02-30 19:45", "must be a time"), ("not a time", "must be a time")],
)
def test_a_malformed_end_time_fails_submitted_shape(tmp_path: Path, end: str, words: str) -> None:
    run = Run(tmp_path)
    report = run.gold()
    broken = copy.deepcopy(report)
    broken["days"][0]["episodes"][0]["end"] = end
    found = run.verdict(broken)
    assert failed(found) == ["submitted-shape"] and words in found["message"]


def test_an_unknown_show_or_episode_fails_submitted_shape(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    unknown = copy.deepcopy(report)
    unknown["days"][0]["episodes"][0]["show"] = "Nothing Here"
    found = run.verdict(unknown)
    assert failed(found) == ["submitted-shape"] and "'Nothing Here' is not a show in the watchlist" in found["message"]
    bad_episode = copy.deepcopy(report)
    bad_episode["days"][0]["episodes"][0]["episode"] = 99
    found = run.verdict(bad_episode)
    assert failed(found) == ["submitted-shape"] and "Glass Harbour has no episode 99" in found["message"]


def test_an_episode_watched_twice_fails_submitted_shape(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    twice = copy.deepcopy(report)
    twice["days"][2]["episodes"] = [dict(twice["days"][0]["episodes"][0], end="2026-03-04 19:45")]
    found = run.verdict(twice)
    assert failed(found) == ["submitted-shape"]


@pytest.mark.parametrize(("run_token", "words"), [("../..", "is not a run token"), ("", "is not a run token"), ("0" * 16, "has no run")])
def test_a_run_that_is_not_this_workspace_s_fails_this_run(tmp_path: Path, run_token: str, words: str) -> None:
    run = Run(tmp_path)
    report = run.gold()
    found = run.verdict({**report, "run": run_token})
    assert failed(found)[0] == "this-run" and words in found["message"] and found["score"] == 0.0


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"blocks": [{"start": "2026-03-02 20:00", "end": "2026-03-02 19:00"}]}, "ends at or before it starts"),
        ({"blocks": [{"start": "2026-03-02 19:00", "end": "2026-03-02 21:00"}, {"start": "2026-03-02 20:00", "end": "2026-03-02 22:00"}]}, "blocks never overlap"),
        ({"blocks": [{"start": "2026-03-01 19:00", "end": "2026-03-01 20:00"}]}, "runs outside"),
        ({"last_day": "2026-03-01"}, "last_day is before first_day"),
    ],
)
def test_a_free_time_file_that_breaks_the_format_fails_sources(tmp_path: Path, change: dict, words: str) -> None:
    run = Run(tmp_path)
    report = run.gold()
    path = tmp_path / "free_time.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), **change}))
    found = run.verdict(report)
    assert "sources" in failed(found) and words in found["message"]


def test_an_edited_report_file_always_gives_a_verdict(tmp_path: Path) -> None:
    """600 mutations of the saved report: one field, at any depth, replaced by an odd JSON value or
    dropped. Every one is a verdict; none is an exception."""
    import random

    run = Run(tmp_path)
    report = run.gold()
    path = tmp_path / "reports" / RUN / "plan.json"
    good = json.loads(path.read_text())
    odd = [None, 0, -1, 1e308, "", "x", [], {}, [1], {"a": 1}, True, "../..", "2026-03-02", "24:00"]
    randomly = random.Random(11)
    for _ in range(600):
        broken = json.loads(json.dumps(good))
        target = randomly.choice(["task", "days", "shows", "day", "show", "drop"])
        if target == "day" and broken["days"]:
            key = randomly.choice(list(broken["days"]))
            broken["days"][key] = randomly.choice([randomly.choice(odd), [randomly.choice(odd)], [{"show": randomly.choice(odd), "episode": randomly.choice(odd), "end": randomly.choice(odd)}]])
        elif target == "show" and broken["shows"]:
            key = randomly.choice(list(broken["shows"]))
            broken["shows"][key] = randomly.choice([randomly.choice(odd), {**broken["shows"][key], randomly.choice(["outcome", "finished_at", "unwatched"]): randomly.choice(odd)}])
        elif target == "drop":
            broken.pop(randomly.choice(list(broken)), None)
        else:
            broken[target] = randomly.choice(odd)
        path.write_text(json.dumps(broken))
        found = run.verdict(report)
        assert isinstance(found["valid"], bool) and 0.0 <= found["score"] <= 1.0, broken


# ----- Boundary -----


def test_an_episode_that_exactly_fills_a_block_is_watched(tmp_path: Path) -> None:
    """Block 1 runs 19:00 to 19:45 and episode 1 runs 45 minutes: it ends exactly at the block's end."""
    report = Run(tmp_path).gold()
    assert [(w["show"], w["episode"], w["end"]) for w in report["days"][0]["episodes"]] == [("Glass Harbour", 1, "2026-03-02 19:45")]


def test_an_episode_one_minute_too_long_wastes_the_block(tmp_path: Path) -> None:
    """Block 2 runs 20:00 to 20:59 and episode 2 runs 60 minutes: nothing else is watched that day."""
    report = Run(tmp_path).gold()
    assert len(report["days"][0]["episodes"]) == 1, "the 59-minute block is wasted"


def test_touching_blocks_never_merge(tmp_path: Path) -> None:
    """2026-03-06 holds 19:00-19:40 and 19:40-20:20. Saltmarsh 2 runs 50 minutes: it fits the 80
    minutes they would make together, and neither of them, so nothing is watched that day."""
    run = Run(tmp_path)
    report = run.gold()
    assert next(entry for entry in report["days"] if entry["date"] == "2026-03-06")["episodes"] == []
    assert next(entry for entry in report["days"] if entry["date"] == "2026-03-07")["episodes"][0]["episode"] == 2


def test_an_episode_ending_exactly_at_the_leaving_time_is_watched(tmp_path: Path) -> None:
    """Glass Harbour leaves at 21:00 and episode 2 ends at 21:00: at or before, so it counts."""
    report = Run(tmp_path).gold()
    day = next(entry for entry in report["days"] if entry["date"] == "2026-03-03")
    assert day["episodes"][0] == {"show": "Glass Harbour", "episode": 2, "end": "2026-03-03 21:00"}


def test_a_show_leaving_mid_block_hands_the_rest_of_it_to_the_next_show(tmp_path: Path) -> None:
    """The block from 21:00 to 22:00 opens after Glass Harbour has left, so The Ninth Kitchen uses it."""
    report = Run(tmp_path).gold()
    day = next(entry for entry in report["days"] if entry["date"] == "2026-03-03")
    assert [(w["show"], w["episode"]) for w in day["episodes"][1:]] == [("The Ninth Kitchen", 1), ("The Ninth Kitchen", 2)]
    left = next(s for s in report["shows"] if s["show"] == "Glass Harbour")
    assert left["outcome"] == "left" and left["unwatched"] == [3, 4]


def test_midnight_opens_the_new_day(tmp_path: Path) -> None:
    """An episode ending at exactly 00:00 counts for the day beginning, as does one ending at 00:25."""
    report = Run(tmp_path).gold()
    assert next(entry for entry in report["days"] if entry["date"] == "2026-03-04")["episodes"] == []
    assert [(w["episode"], w["end"]) for w in next(e for e in report["days"] if e["date"] == "2026-03-05")["episodes"]] == [
        (3, "2026-03-05 00:00"),
        (1, "2026-03-05 00:25"),
    ]


def test_a_week_where_nothing_fits(tmp_path: Path) -> None:
    run = Run(tmp_path, watchlist="watchlist_tiny.json", free_time="free_time_tiny.json")
    report = run.gold()
    assert [entry["episodes"] for entry in report["days"]] == [[], []]
    assert report["shows"] == [{"show": "Low Tide Radio", "outcome": "out-of-time", "finished_at": None, "unwatched": [1]}]
    assert run.verdict()["valid"]


def test_a_show_that_leaves_before_the_watchlist_reaches_it(tmp_path: Path) -> None:
    run = Run(tmp_path, watchlist="watchlist_early.json", free_time="free_time_early.json")
    report = run.gold()
    assert [(s["show"], s["outcome"]) for s in report["shows"]] == [("Orbital Rooms", "finished"), ("Low Tide Radio", "left")]
    assert run.verdict()["valid"]


def test_the_watchlist_finishing_early_leaves_empty_days(tmp_path: Path) -> None:
    report = Run(tmp_path).gold()
    assert next(entry for entry in report["days"] if entry["date"] == "2026-03-08")["episodes"] == []
    assert all(s["outcome"] != "out-of-time" for s in report["shows"])


# ----- The per-call checks -----


def test_every_tool_has_both_checks_on_its_module(tmp_path: Path) -> None:
    """NanoAgent calls verify_input and verify_output on every tool call, so every Tool must resolve
    to a module exposing both. A shared check reached by an aliased import would pass the unit tests
    and still fail the moment the host called it."""
    from contract import Tool

    assert set(verifier.TOOLS) == set(Tool)
    for tool in Tool:
        module = verifier.TOOLS[tool]
        for name in ("verify_input", "verify_output"):
            assert callable(module.__dict__.get(name)), f"{tool.value}: {module.__name__} has no {name}"


def test_verify_input_answers_for_every_tool(tmp_path: Path) -> None:
    run = Run(tmp_path)
    from contract import Tool

    valid = {
        Tool.READ_WATCHLIST: build_output({"watchlist": WATCHLIST}, WatchlistInput),
        Tool.READ_FREE_TIME: run.given,
        Tool.PLAN_WEEK: run.given,
        Tool.MERGE_FREE_TIME: run.given,
        Tool.TOTAL_RUNTIME: run.given,
        Tool.REPORT_SCHEDULE: build_output({"task": run.task, "days": [], "shows": []}, ReportInput),
    }
    for tool, value in valid.items():
        found = verifier.verify_input(tool.value, value)
        assert found["valid"] is True, (tool.value, found["message"])


def test_verify_output_refuses_an_answer_key_that_breaks_the_rules(tmp_path: Path) -> None:
    run = Run(tmp_path)
    key = plain_output(run.key)
    assert verifier.verify_output("plan_week", run.given, build_output(key, KeyOutput), str(tmp_path))["valid"]
    key["days"][0] = {**key["days"][0], "episodes": []}
    found = verifier.verify_output("plan_week", run.given, build_output(key, KeyOutput), str(tmp_path))
    assert not found["valid"] and "days are not the ones the rules give" in found["message"]


def test_the_distractors_are_checked_against_what_they_claim(tmp_path: Path) -> None:
    """merge_free_time and total_runtime are honest tools: their checks hold them to their own job,
    not to the task's rules."""
    run = Run(tmp_path)
    merged = merge_free_time(run.given, tmp_path)
    assert verifier.verify_output("merge_free_time", run.given, merged, str(tmp_path))["valid"]
    assert merged.merged == 2, "the pairs on 2026-03-03 and 2026-03-06 each touch"
    wrong = build_output({**plain_output(merged), "merged": 4}, MergedOutput)
    assert not verifier.verify_output("merge_free_time", run.given, wrong, str(tmp_path))["valid"]
    totals = total_runtime(run.given, tmp_path)
    assert verifier.verify_output("total_runtime", run.given, totals, str(tmp_path))["valid"]
    assert totals.minutes == 45 + 60 + 50 + 40 + 30 + 30 + 60 + 25 + 50


# ----- The read-watchlist task -----


def test_the_read_watchlist_task_verdict(tmp_path: Path) -> None:
    stage(tmp_path, WATCHLIST)
    given = build_output({"watchlist": WATCHLIST}, WatchlistInput)
    answer = read_watchlist(given, tmp_path)
    found = verifier.verify_task("read-watchlist", given, answer, None, str(tmp_path))
    assert found["valid"] and found["score"] == 1.0
    wrong = plain_output(answer)
    wrong["watchlist"]["shows"][0]["episodes"][0]["minutes"] = 44
    found = verifier.verify_task("read-watchlist", given, build_output(wrong, WatchlistOutput), None, str(tmp_path))
    assert not found["valid"] and found["score"] == 0.0 and "episodes are not the file's" in found["message"]


# ----- The verdict's own shape -----


def test_every_verdict_entry_has_the_same_keys_and_says_why(tmp_path: Path) -> None:
    run = Run(tmp_path)
    report = run.gold()
    broken = copy.deepcopy(report)
    broken["days"][0]["episodes"] = []
    for found in (run.verdict(report), run.verdict(broken), run.verdict({**report, "run": "0" * 16})):
        entries = found["details"]["constraints"]
        order = [entry["id"] for entry in entries]
        assert order == list(TEXT)
        for position, entry in enumerate(entries):
            assert set(entry) == {"id", "constraint", "ok", "expected", "actual", "message"}
            assert (entry["message"] == "") == (entry["ok"] is True)
            if entry["ok"] is None:
                blocking = entry["message"].removeprefix("Not checked: ").removesuffix(" did not hold.").split(" and ")
                assert all(name in order[:position] for name in blocking), entry
        wrong = [entry for entry in entries if entry["ok"] is False]
        if wrong:
            more = f" (+{len(wrong) - 1} more)" if len(wrong) > 1 else ""
            assert found["message"] == f"{wrong[0]['id']}: {wrong[0]['message'].removesuffix('.')}{more}"


def test_the_readme_lists_every_constraint_as_the_verifier_names_it() -> None:
    import re

    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\d+) \| `([a-z-]+)` \| ([^|]+) \|", readme, re.MULTILINE)
    assert [(int(number), name, text.strip()) for number, name, text in rows] == [(number, *entry) for number, entry in enumerate(TEXT.items(), 1)]
