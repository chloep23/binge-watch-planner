"""read_sources: the watchlist and the week, both recomputed from the files."""

from .checks import result, verify_sources_input
from .civil import day_minutes, minutes_of
from .rules import load

verify_input = verify_sources_input


def verify_output(input_value, output_value, workspace):
    shows, week, source, problem = load(workspace, input_value.watchlist, input_value.free_time)
    if problem:
        return result(False, problem)
    if output_value.source_sha256 != source:
        return result(False, "source_sha256 is not the hash of the two source files")
    given = output_value.watchlist.shows
    if [show.title for show in given] != [show["title"] for show in shows]:
        return result(False, "the shows are not the watchlist's, in its order")
    for show, want in zip(given, shows, strict=True):
        if [(item.number, item.minutes) for item in show.episodes] != [(i["number"], i["minutes"]) for i in want["episodes"]]:
            return result(False, f"{show.title}: the episodes are not the file's, in its order")
        if (None if show.leaves is None else minutes_of(show.leaves)) != want["leaves"]:
            return result(False, f"{show.title}: leaves reads {show.leaves!r}, not the file's")
    blocks = [(minutes_of(block.start), minutes_of(block.end)) for block in output_value.week.blocks]
    if blocks != [(block["start"], block["end"]) for block in week["blocks"]]:
        return result(False, "the blocks are not the free-time file's, in its order")
    if (day_minutes(output_value.week.first_day), day_minutes(output_value.week.last_day)) != (week["first"], week["last"]):
        return result(False, "the week is not the free-time file's")
    return result(True, "both files are read as they stand", shows=len(given), blocks=len(blocks))
