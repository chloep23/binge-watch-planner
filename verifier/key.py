"""plan_week: the answer key, re-simulated."""

from .checks import result, verify_sources_input
from .rules import expected, load

verify_input = verify_sources_input


def given_days(days):
    return [(entry.date, [(watch.show, watch.episode, watch.end) for watch in entry.episodes]) for entry in days]


def given_shows(shows):
    return [(entry.show, entry.outcome.value, entry.finished_at, list(entry.unwatched)) for entry in shows]


def verify_output(input_value, output_value, workspace):
    shows, week, source, problem = load(workspace, input_value.watchlist, input_value.free_time)
    if problem:
        return result(False, problem)
    if output_value.source_sha256 != source:
        return result(False, "source_sha256 is not the hash of the two source files")
    wanted_days, wanted_shows = expected(shows, week)
    if given_days(output_value.days) != wanted_days:
        return result(False, "the answer key's days are not the ones the rules give")
    if given_shows(output_value.shows) != wanted_shows:
        return result(False, "the answer key's show outcomes are not the ones the rules give")
    return result(True, "the answer key follows the rules", days=len(wanted_days), shows=len(wanted_shows))
