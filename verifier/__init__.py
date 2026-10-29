"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import freetime, key, merged, report, runtime, task, watchlist

TOOLS = {
    Tool.READ_WATCHLIST: watchlist,
    Tool.READ_FREE_TIME: freetime,
    Tool.REPORT_SCHEDULE: report,
    Tool.PLAN_WEEK: key,
    Tool.MERGE_FREE_TIME: merged,
    Tool.TOTAL_RUNTIME: runtime,
}
# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {Task.WEEK_PLAN: task.verify_task, Task.READ_WATCHLIST: watchlist.verify_task}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
