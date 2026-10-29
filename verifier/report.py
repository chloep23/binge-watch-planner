"""report_schedule: the call and the merged report it returns."""

from .checks import result, run_folder, sources_problem
from .civil import day_minutes, days_between, minutes_of
from .rules import load


def verify_input(value):
    problem = sources_problem(value.task)
    if problem:
        return result(False, problem)
    for name, named in (("day", [entry.date for entry in value.days]), ("show", [entry.show for entry in value.shows])):
        if len(set(named)) != len(named):
            return result(False, f"a {name} is named twice in one call")
    for entry in value.days:
        if day_minutes(entry.date) is None:
            return result(False, f'{entry.date!r} is not a day "YYYY-MM-DD"')
        for watch in entry.episodes:
            if minutes_of(watch.end) is None:
                return result(False, f'{watch.show} {watch.episode}: end must be a time "YYYY-MM-DD HH:MM", not {watch.end!r}')
    for entry in value.shows:
        if entry.finished_at is not None and minutes_of(entry.finished_at) is None:
            return result(False, f"{entry.show}: finished_at must be a time or null, not {entry.finished_at!r}")
    return result(True, "input is valid", days=len(value.days), shows=len(value.shows))


def verify_output(input_value, output_value, workspace):
    shows, week, _, problem = load(workspace, input_value.task.watchlist, input_value.task.free_time)
    if problem:
        return result(False, problem)
    days = days_between(week["first"], week["last"])
    titles = [show["title"] for show in shows]
    report = output_value.report
    if output_value.path != f"{run_folder(report.run)}/plan.json":
        return result(False, f"the report path reads {output_value.path!r}, not this run's")
    if output_value.covered != len(report.days):
        return result(False, f"covered reads {output_value.covered}, but the report holds {len(report.days)} days")
    if output_value.complete != (len(report.days) == len(days) and len(report.shows) == len(titles)):
        return result(False, f"complete reads {output_value.complete}, which is not whether every day and show is covered")
    if [entry.date for entry in report.days] != [day for day in days if day in {e.date for e in report.days}]:
        return result(False, "the merged report's days are not in the week's order")
    for entry in input_value.days:
        if not any(held.date == entry.date for held in report.days):
            return result(False, f"{entry.date} is not in the merged report")
    return result(True, "the merged report holds this call", covered=output_value.covered)
