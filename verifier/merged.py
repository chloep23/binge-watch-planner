"""merge_free_time: checked against what merging actually means, not against the task's rules."""

from .checks import result, verify_sources_input
from .civil import stamp_text
from .rules import load

verify_input = verify_sources_input


def verify_output(input_value, output_value, workspace):
    _, week, _, problem = load(workspace, input_value.watchlist, input_value.free_time)
    if problem:
        return result(False, problem)
    spans = []
    for block in week["blocks"]:
        if spans and block["start"] <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], block["end"])
        else:
            spans.append([block["start"], block["end"]])
    given = [(block.start, block.end) for block in output_value.blocks]
    if given != [(stamp_text(start), stamp_text(end)) for start, end in spans]:
        return result(False, "the merged blocks are not the blocks that touch, joined")
    if output_value.merged != len(week["blocks"]) - len(spans):
        return result(False, f"merged reads {output_value.merged}, not {len(week['blocks']) - len(spans)}")
    return result(True, "the blocks that touch are joined", spans=len(spans))
