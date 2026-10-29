"""The week-plan verdict: 12 constraints, in order, on the answer key, the run the submission
names, the files its reads left behind, the saved and submitted report, and the plan itself.

The verdict is valid only when every one holds. A failure among the first 9 -- the sources and
the report's integrity -- scores 0; otherwise the score is the share of the week's days and the
watchlist's shows that are exactly right, so a plan right about 6 of 7 days and 2 of 3 shows
scores 8/10.

Every file the verdict reads is the named run's own (reports/<run>/), so two task calls in one
workspace are judged apart.
"""

from pathlib import Path

from .checks import REPORT, constraint, read_json, result, run_folder, run_problem, summary
from .civil import day_text, days_between, minutes_of
from .rules import expected, load

TEXT = {
    "answer-key": "The answer key planned this task's files",
    "sources": "The watchlist and the free-time file are well formed",
    "answer-key-right": "The answer key follows the watching rules",
    "this-run": "The report names a run of this workspace",
    "read-sources": "read_watchlist and read_free_time read this task's files in this run",
    "report-saved": "report_schedule saved this run's report for this task",
    "submitted-task": "The submitted report is for this task",
    "submitted-shape": "The submitted report is well formed",
    "submitted-as-saved": "The submitted report equals the saved report",
    "all-days": "Every day of the week is reported exactly once, in order",
    "episodes-exact": "Each day lists exactly the episodes ending that day, in the order watched",
    "shows-exact": "Each show's outcome, finishing time and unwatched episodes are right",
}
ORDER = tuple(TEXT)
GATES = ORDER[:9]
ANSWER_CHECKS = ORDER[9:]
MOST_NAMED = 3
SUBMIT = "Submit the report the last report_schedule call returned, as it is."
RECEIPTS = (("watchlist.json", "read_watchlist", "watchlist"), ("free_time.json", "read_free_time", "free_time"))


def named(names):
    shown = ", ".join(str(name) for name in names[:MOST_NAMED])
    return shown + (f" and {len(names) - MOST_NAMED} more" if len(names) > MOST_NAMED else "")


def also(words, names):
    return f" Also {words}: {named(names[1:])}." if len(names) > 1 else ""


def saved_report(workspace, run):
    """(the run's saved report, None) or (None, what is wrong with it)."""
    where = f"{run_folder(run)}/{REPORT}"
    found, problem = read_json(Path(workspace) / where)
    if problem == "missing":
        return None, f"no report at {where}: report_schedule never saved this task's plan"
    if problem:
        return None, f"{where} is not a report: {problem}"
    if not isinstance(found, dict) or not isinstance(found.get("days"), dict) or not isinstance(found.get("shows"), dict):
        return None, f"{where} was altered after report_schedule: it must hold task, days and shows"
    if not isinstance(found.get("task"), dict):
        return None, f"{where} was altered after report_schedule: it names no task"
    for day, watches in found["days"].items():
        if not isinstance(day, str) or not isinstance(watches, list):
            return None, f"{where} was altered after report_schedule: {day!r} must hold a list of episodes"
        for watch in watches:
            if not isinstance(watch, dict) or not isinstance(watch.get("show"), str) or not isinstance(watch.get("end"), str):
                return None, f"{where} was altered after report_schedule: an episode of {day} must hold a show and an end"
            if not isinstance(watch.get("episode"), int) or isinstance(watch.get("episode"), bool):
                return None, f"{where} was altered after report_schedule: an episode number of {day} must be a whole number"
    for title, entry in found["shows"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("outcome"), str) or not isinstance(entry.get("unwatched"), list):
            return None, f"{where} was altered after report_schedule: {title}'s entry must hold an outcome and its unwatched episodes"
        if entry.get("finished_at") is not None and not isinstance(entry["finished_at"], str):
            return None, f"{where} was altered after report_schedule: {title}'s finished_at must be a time or null"
    return found, None


def submitted(output):
    """The submission's days and shows, in the shape the rules compare."""
    days = [(entry.date, [(watch.show, watch.episode, watch.end) for watch in entry.episodes]) for entry in output.days]
    shows = [(entry.show, entry.outcome.value, entry.finished_at, list(entry.unwatched)) for entry in output.shows]
    return days, shows


def shape_problem(week_days, titles, episodes_of, days, shows):
    """Why the submitted report cannot be judged, or None."""
    listed = [day for day, _ in days]
    unknown = [day for day in listed if day not in week_days]
    if unknown:
        return f"{unknown[0]!r} is not a day of this week"
    repeated = [day for day in listed if listed.count(day) > 1]
    if repeated:
        return f"{repeated[0]} is reported twice"
    named_shows = [title for title, *_ in shows]
    unknown = [title for title in named_shows if title not in titles]
    if unknown:
        return f"{unknown[0]!r} is not a show in the watchlist"
    repeated = [title for title in named_shows if named_shows.count(title) > 1]
    if repeated:
        return f"{repeated[0]!r} is reported twice"
    seen = set()
    for day, watches in days:
        for title, number, end in watches:
            if title not in titles:
                return f"{title!r} is not a show in the watchlist"
            if number not in episodes_of[title]:
                return f"{title} has no episode {number}"
            if (title, number) in seen:
                return f"{title} {number} is watched twice"
            seen.add((title, number))
            if minutes_of(end) is None:
                return f'{title} {number}: end must be a time "YYYY-MM-DD HH:MM", not {end!r}'
            if day_text(minutes_of(end)) != day:
                return f"{title} {number} ends at {end}, which is not {day}: an episode counts for the day it ends on"
    for title, _, at, unwatched in shows:
        if at is not None and minutes_of(at) is None:
            return f"{title}: finished_at must be a time or null, not {at!r}"
        unknown = [number for number in unwatched if number not in episodes_of[title]]
        if unknown:
            return f"{title} has no episode {unknown[0]}"
    return None


def verify_task(arguments, output, reference, workspace):
    """The verdict on a submitted week-plan report (see the module's docstring)."""
    checks = {}

    def put(identifier, ok, expected_value=None, actual=None, message=""):
        checks[identifier] = constraint(identifier, TEXT[identifier], ok, expected_value, actual, message)

    def skip(identifier, *needs):
        blocking = [need for need in needs if checks[need]["ok"] is not True]
        checks[identifier] = constraint(identifier, TEXT[identifier], None, message=f"Not checked: {' and '.join(blocking)} did not hold.")

    def hold(*identifiers):
        return all(checks[identifier]["ok"] is True for identifier in identifiers)

    # 1-3: the sources and the answer key.
    shows, week, source, problem = load(workspace, arguments.watchlist, arguments.free_time)
    if reference is None:
        put("answer-key", False, None, None, f"No answer key: plan_week never read {arguments.watchlist}.")
    elif problem is None and reference.source_sha256 != source:
        put("answer-key", False, source[:16], reference.source_sha256[:16], "The answer key read other files than this task names.")
    else:
        put("answer-key", True)
    put("sources", problem is None, None, None, problem or "")
    wanted_days, wanted_shows, week_days, titles, episodes_of = [], [], [], [], {}
    if hold("answer-key", "sources"):
        wanted_days, wanted_shows = expected(shows, week)
        week_days = days_between(week["first"], week["last"])
        titles = [show["title"] for show in shows]
        episodes_of = {show["title"]: {item["number"] for item in show["episodes"]} for show in shows}
        from .key import given_days, given_shows

        if given_days(reference.days) != wanted_days:
            put("answer-key-right", False, None, None, "The answer key's days are not the ones the rules give.")
        elif given_shows(reference.shows) != wanted_shows:
            put("answer-key-right", False, None, None, "The answer key's show outcomes are not the ones the rules give.")
        else:
            put("answer-key-right", True)
    else:
        skip("answer-key-right", "answer-key", "sources")

    # 4-5: the run, and what its read tools left behind.
    run = output.run
    problem = run_problem(workspace, run)
    put("this-run", problem is None, None, run, problem or "")
    if hold("this-run", "sources"):
        message = ""
        for name, tool, field in RECEIPTS:
            where = f"{run_folder(run)}/{name}"
            found, trouble = read_json(Path(workspace) / where)
            wanted_name = arguments.watchlist if field == "watchlist" else arguments.free_time
            if trouble == "missing":
                message = f"{tool} was never called in run {run} (no {where}): read the files before reporting."
            elif trouble:
                message = f"{where} is not a receipt: {trouble}."
            elif not isinstance(found, dict) or found.get("run") != run:
                message = f"{where} was altered after {tool}: it does not name run {run}."
            elif found.get(field) != wanted_name:
                message = f"{tool} read {found.get(field)!r}, not this task's {wanted_name!r}."
            if message:
                break
        put("read-sources", not message, None, None, message)
    else:
        skip("read-sources", "this-run", "sources")

    # 6-9: the saved and the submitted report.
    saved = None
    if hold("this-run"):
        saved, problem = saved_report(workspace, run)
        wanted_task = {"watchlist": arguments.watchlist, "free_time": arguments.free_time}
        if saved is not None and saved["task"] != wanted_task:
            saved, problem = None, f"the saved report is for another task: {saved['task']}"
        put("report-saved", saved is not None, None, None, problem or "")
    else:
        skip("report-saved", "this-run")
    given_task = {"watchlist": output.task.watchlist, "free_time": output.task.free_time}
    wanted_task = {"watchlist": arguments.watchlist, "free_time": arguments.free_time}
    put("submitted-task", given_task == wanted_task, wanted_task, given_task, f"The submitted report names {given_task}, not this task's files. {SUBMIT}")
    days, shows_given = submitted(output)
    if hold("sources", "submitted-task"):
        problem = shape_problem(week_days, titles, episodes_of, days, shows_given)
        put("submitted-shape", problem is None, None, None, f"The submitted report is malformed: {problem}" if problem else "")
    else:
        skip("submitted-shape", "sources", "submitted-task")
    if saved is not None and hold("submitted-shape"):
        held_days = {day: [(w["show"], w["episode"], w["end"]) for w in watches] for day, watches in saved["days"].items()}
        held_shows = {title: (entry["outcome"], entry["finished_at"], list(entry["unwatched"])) for title, entry in saved["shows"].items()}
        difference = ""
        for day, watches in days:
            if day not in held_days:
                difference = f"it adds {day}, which the saved report does not hold"
            elif held_days[day] != watches:
                difference = f"{day} reads differently in the submission than in the saved report"
            if difference:
                break
        if not difference:
            for title, outcome, at, unwatched in shows_given:
                if title not in held_shows:
                    difference = f"it adds {title}, which the saved report does not hold"
                elif held_shows[title] != (outcome, at, unwatched):
                    difference = f"{title} reads differently in the submission than in the saved report"
                if difference:
                    break
        if not difference and (len(held_days) != len(days) or len(held_shows) != len(shows_given)):
            difference = "it leaves out something the saved report holds"
        put("submitted-as-saved", not difference, len(held_days), len(days), f"The submitted report is not the saved report {run_folder(run)}/{REPORT}: {difference}. {SUBMIT}")
    else:
        skip("submitted-as-saved", "report-saved", "submitted-shape")

    # 10-12: the plan itself.
    right = None
    if hold("answer-key-right", "submitted-shape"):
        listed = [day for day, _ in days]
        missing = [day for day in week_days if day not in listed]
        if missing or listed != sorted(listed):
            message = (
                f"{len(missing)} of the {len(week_days)} days {'is' if len(missing) == 1 else 'are'} not reported ({named(missing)}): report every day, even one with nothing watched."
                if missing
                else "the days are not in order"
            )
            put("all-days", False, len(week_days), len(listed), message)
        else:
            put("all-days", True)
        by_day = dict(days)
        wrong = [day for day, watches in wanted_days if day in by_day and by_day[day] != watches]
        if wrong:
            day = wrong[0]
            want = dict(wanted_days)[day]
            got = by_day[day]
            shortfall = [entry for entry in want if entry not in got]
            extra = [entry for entry in got if entry not in want]
            if shortfall:
                title, number, end = shortfall[0]
                detail = f"{title} {number} ends at {end} that day and is not reported"
            elif extra:
                title, number, end = extra[0]
                detail = f"{title} {number} is reported ending at {end}, which the rules do not give"
            else:
                detail = "the episodes are in the wrong order"
            put("episodes-exact", False, {day: want}, {day: got}, f"{day} is wrong: {detail}.{also('wrong', wrong)}")
        else:
            put("episodes-exact", True)
        by_show = {title: entry for title, *entry in ((t, o, a, u) for t, o, a, u in shows_given)}
        wrong_shows = [title for title, outcome, at, unwatched in wanted_shows if by_show.get(title) != [outcome, at, unwatched]]
        if wrong_shows:
            title = wrong_shows[0]
            outcome, at, unwatched = next((o, a, u) for t, o, a, u in wanted_shows if t == title)
            got = by_show.get(title)
            detail = (
                "it is not reported" if got is None
                else f"it reads {got[0]}{'' if got[1] is None else ' at ' + got[1]} with {got[2] or 'no'} unwatched, but the rules give {outcome}{'' if at is None else ' at ' + at} with {unwatched or 'no'} unwatched"
            )
            put("shows-exact", False, {title: [outcome, at, unwatched]}, {title: got}, f"{title} is wrong: {detail}.{also('wrong', wrong_shows)}")
        else:
            put("shows-exact", True)
        right = sum(1 for day, watches in wanted_days if day in by_day and by_day[day] == watches)
        right += sum(1 for title, outcome, at, unwatched in wanted_shows if by_show.get(title) == [outcome, at, unwatched])
    else:
        for identifier in ANSWER_CHECKS:
            skip(identifier, "answer-key-right", "submitted-shape")

    constraints = [checks[identifier] for identifier in ORDER]
    valid = all(entry["ok"] is True for entry in constraints)
    rows = len(wanted_days) + len(wanted_shows)
    if any(checks[identifier]["ok"] is not True for identifier in GATES) or right is None or not rows:
        score = 0.0
    else:
        score = right / rows
    details = {"constraints": constraints, "days": len(wanted_days) or None, "shows": len(wanted_shows) or None}
    if right is not None:
        details["right"] = right
    if valid:
        return result(True, f"All {len(constraints)} checks hold: {len(wanted_days)} days and {len(wanted_shows)} shows planned by the rules.", score=1.0, **details)
    return result(False, summary(constraints), score=min(score, 0.99), **details)
