"""read_watchlist, and the read-watchlist task's verdict."""

import json

from .checks import constraint, result, summary
from .rules import parse_watchlist, read_text, sha256_text


def verify_input(value):
    if not isinstance(value.watchlist, str) or not value.watchlist.strip():
        return result(False, "the watchlist is named by its path in the workspace")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    text, problem = read_text(workspace, input_value.watchlist)
    if problem:
        return result(False, problem)
    try:
        wanted, problem = parse_watchlist(json.loads(text))
    except (ValueError, RecursionError) as error:
        return result(False, f"{input_value.watchlist} is not JSON: {error}")
    if problem:
        return result(False, f"{input_value.watchlist}: {problem}")
    if output_value.source_sha256 != sha256_text(text):
        return result(False, "source_sha256 is not the sha256 of the watchlist file")
    given = output_value.watchlist.shows
    if [show.title for show in given] != [show["title"] for show in wanted]:
        return result(False, "the shows are not the file's, in its order")
    for show, want in zip(given, wanted, strict=True):
        if [(item.number, item.minutes) for item in show.episodes] != [(item["number"], item["minutes"]) for item in want["episodes"]]:
            return result(False, f"{show.title}: the episodes are not the file's, in its order")
        from .civil import minutes_of

        if (None if show.leaves is None else minutes_of(show.leaves)) != want["leaves"]:
            return result(False, f"{show.title}: leaves reads {show.leaves!r}, not the file's")
    return result(True, "the watchlist is the file's", shows=len(given))


def verify_task(arguments, output, reference, workspace):
    """The read-watchlist task: its one tool's output, checked again as the task's answer."""
    found = verify_output(arguments, output, workspace)
    entry = constraint("watchlist", "The watchlist is the file's, in its order", found["valid"], message=found["message"])
    if found["valid"]:
        return result(True, "The watchlist is read as the file states it.", constraints=[entry])
    return result(False, summary([entry]), score=0.0, constraints=[entry])
