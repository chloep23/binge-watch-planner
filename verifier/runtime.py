"""total_runtime: episode counts and totals, recomputed."""

from .checks import result, verify_sources_input
from .rules import load

verify_input = verify_sources_input


def verify_output(input_value, output_value, workspace):
    shows, week, _, problem = load(workspace, input_value.watchlist, input_value.free_time)
    if problem:
        return result(False, problem)
    wanted = [(show["title"], len(show["episodes"]), sum(item["minutes"] for item in show["episodes"])) for show in shows]
    if [(entry.show, entry.episodes, entry.minutes) for entry in output_value.shows] != wanted:
        return result(False, "the shows' episode counts and runtimes are not the watchlist's")
    if output_value.minutes != sum(minutes for _, _, minutes in wanted):
        return result(False, f"minutes reads {output_value.minutes}, not {sum(m for _, _, m in wanted)}")
    free = sum(block["end"] - block["start"] for block in week["blocks"])
    if output_value.free_minutes != free:
        return result(False, f"free_minutes reads {output_value.free_minutes}, not {free}")
    return result(True, "the runtimes are the watchlist's", minutes=output_value.minutes)
