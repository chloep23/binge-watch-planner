"""read_free_time: the week and its blocks, recomputed from the file."""

import json

from .checks import result, verify_sources_input
from .civil import minutes_of
from .rules import parse_week, read_text, sha256_text

verify_input = verify_sources_input


def verify_output(input_value, output_value, workspace):
    text, problem = read_text(workspace, input_value.free_time)
    if problem:
        return result(False, problem)
    try:
        wanted, problem = parse_week(json.loads(text))
    except (ValueError, RecursionError) as error:
        return result(False, f"{input_value.free_time} is not JSON: {error}")
    if problem:
        return result(False, f"{input_value.free_time}: {problem}")
    if output_value.source_sha256 != sha256_text(text):
        return result(False, "source_sha256 is not the sha256 of the free-time file")
    week = output_value.week
    given = [(minutes_of(block.start), minutes_of(block.end)) for block in week.blocks]
    if given != [(block["start"], block["end"]) for block in wanted["blocks"]]:
        return result(False, "the blocks are not the file's, in its order")
    from .civil import day_minutes

    if (day_minutes(week.first_day), day_minutes(week.last_day)) != (wanted["first"], wanted["last"]):
        return result(False, "the week is not the file's")
    return result(True, "the week is the file's", blocks=len(given))
