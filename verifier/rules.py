"""The watching rules, recomputed from the source files alone.

This is the verifier's own reading of the watchlist and the free-time file and its own run of
the simulation. It shares no code with the plugin: the plugin keeps time with ``datetime``,
this keeps it with integers (``civil.py``), and the two are compared on every fixture, so a
tool and the check of that tool cannot be wrong in the same way.
"""

import hashlib
import json
from pathlib import Path

from .civil import MINUTES_A_DAY, day_minutes, day_text, days_between, minutes_of, stamp_text

FINISHED, LEFT, OUT_OF_TIME = "finished", "left", "out-of-time"


def whole(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def parse_watchlist(data):
    """(the shows as plain values, None) or (None, what is wrong with the watchlist)."""
    if not isinstance(data, dict) or not isinstance(data.get("shows"), list) or not data["shows"]:
        return None, "a watchlist holds a shows list with at least one show"
    titles, shows = set(), []
    for entry in data["shows"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("title"), str) or not entry["title"].strip():
            return None, "every show has a title"
        title = entry["title"]
        if title in titles:
            return None, f"show {title!r} is listed twice"
        titles.add(title)
        if not isinstance(entry.get("episodes"), list) or not entry["episodes"]:
            return None, f"{title}: a show has at least one episode"
        numbers, episodes = set(), []
        for item in entry["episodes"]:
            if not isinstance(item, dict) or not whole(item.get("number")) or not whole(item.get("minutes")):
                return None, f"{title}: every episode has a whole number and minutes above 0"
            if item["number"] in numbers:
                return None, f"{title}: episode {item['number']} is listed twice"
            numbers.add(item["number"])
            episodes.append({"number": item["number"], "minutes": item["minutes"]})
        leaves = entry.get("leaves")
        if leaves is not None and minutes_of(leaves) is None:
            return None, f'{title}: leaves must be a date and time "YYYY-MM-DD HH:MM", not {leaves!r}'
        shows.append({"title": title, "leaves": None if leaves is None else minutes_of(leaves), "episodes": episodes})
    return shows, None


def parse_week(data):
    """(the week as plain values, None) or (None, what is wrong with the free-time file)."""
    if not isinstance(data, dict):
        return None, "a free-time file is a JSON object"
    first, last = day_minutes(data.get("first_day")), day_minutes(data.get("last_day"))
    if first is None or last is None:
        return None, 'first_day and last_day must be days "YYYY-MM-DD"'
    if last < first:
        return None, "last_day is before first_day"
    if not isinstance(data.get("blocks"), list):
        return None, "a free-time file holds a blocks list"
    closes = last + MINUTES_A_DAY - 1
    blocks, previous = [], None
    for position, entry in enumerate(data["blocks"], 1):
        if not isinstance(entry, dict):
            return None, f"block {position} is not an object"
        start, end = minutes_of(entry.get("start")), minutes_of(entry.get("end"))
        if start is None or end is None:
            return None, f'block {position}: start and end must be times "YYYY-MM-DD HH:MM"'
        if end <= start:
            return None, f"block {position} ends at or before it starts"
        if start < first or end > closes:
            return None, f"block {position} runs outside {data['first_day']} to {data['last_day']} 23:59"
        if previous is not None and start < previous:
            return None, f"block {position} starts before block {position - 1} ends: blocks never overlap"
        previous = end
        blocks.append({"start": start, "end": end})
    return {"first": first, "last": last, "blocks": blocks}, None


def simulate(shows, week):
    """The one schedule the rules give: ({day: [(show, episode, end)]}, [(show, outcome, finished_at, unwatched)])."""
    watched = []
    finished_at, left = {}, set()
    index, episode = 0, 0
    for block in week["blocks"]:
        now = block["start"]
        while index < len(shows):
            show = shows[index]
            if episode >= len(show["episodes"]):
                index, episode = index + 1, 0
                continue
            if show["leaves"] is not None and show["leaves"] <= now:
                left.add(index)
                index, episode = index + 1, 0
                continue
            finish = now + show["episodes"][episode]["minutes"]
            if finish > block["end"]:
                break  # it does not fit: the rest of this block is wasted
            if show["leaves"] is not None and finish > show["leaves"]:
                left.add(index)
                index, episode = index + 1, 0
                continue
            watched.append((show["title"], show["episodes"][episode]["number"], finish))
            now, episode = finish, episode + 1
            if episode == len(show["episodes"]):
                finished_at[index] = finish
                index, episode = index + 1, 0

    closes = week["blocks"][-1]["end"] if week["blocks"] else week["first"]
    days = {day: [] for day in days_between(week["first"], week["last"])}
    for title, number, end in watched:
        days.setdefault(day_text(end), []).append((title, number, end))
    seen = {(title, number) for title, number, _ in watched}
    outcomes = []
    for position, show in enumerate(shows):
        unwatched = [item["number"] for item in show["episodes"] if (show["title"], item["number"]) not in seen]
        if not unwatched:
            outcomes.append((show["title"], FINISHED, finished_at[position], []))
        elif position in left or (show["leaves"] is not None and show["leaves"] <= closes):
            outcomes.append((show["title"], LEFT, None, unwatched))
        else:
            outcomes.append((show["title"], OUT_OF_TIME, None, unwatched))
    return days, outcomes


def expected(shows, week):
    """What the answer must be, as the submission writes it: days in order, then shows in order."""
    days, outcomes = simulate(shows, week)
    return (
        [
            (day, [(title, number, stamp_text(end)) for title, number, end in sorted(watches, key=lambda watch: watch[2])])
            for day, watches in sorted(days.items())
        ],
        [(title, outcome, None if at is None else stamp_text(at), unwatched) for title, outcome, at, unwatched in outcomes],
    )


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sources_sha256(watchlist_text, free_time_text):
    return sha256_text(f"{sha256_text(watchlist_text)}:{sha256_text(free_time_text)}")


def read_text(workspace, name):
    """(the file's text, None) or (None, why it cannot be read)."""
    if not isinstance(name, str) or not name:
        return None, f"{name!r} is not a file name"
    relative = Path(name)
    root = Path(workspace).resolve()
    path = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(root) or path == root:
        return None, f"{name!r} must name a file inside the workspace"
    if not path.is_file():
        return None, f"no file at {name}"
    if path.stat().st_size > 4_000_000:
        return None, f"{name} is too large to read"
    return path.read_text(encoding="utf-8"), None


def load(workspace, watchlist_name, free_time_name):
    """(the shows, the week, the source hash, None) or (None, None, None, what is wrong)."""
    watchlist_text, problem = read_text(workspace, watchlist_name)
    if problem:
        return None, None, None, problem
    free_time_text, problem = read_text(workspace, free_time_name)
    if problem:
        return None, None, None, problem
    try:
        watchlist_data, week_data = json.loads(watchlist_text), json.loads(free_time_text)
    except (ValueError, RecursionError) as error:
        return None, None, None, f"a source file is not JSON: {error}"
    shows, problem = parse_watchlist(watchlist_data)
    if problem:
        return None, None, None, f"{watchlist_name}: {problem}"
    week, problem = parse_week(week_data)
    if problem:
        return None, None, None, f"{free_time_name}: {problem}"
    return shows, week, sources_sha256(watchlist_text, free_time_text), None
