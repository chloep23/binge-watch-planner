"""The watching rules, as one simulation.

Shows are watched in watchlist order and episodes in theirs; a show is finished, or has left,
before the next one starts. An episode must fit whole inside one block, and blocks never merge,
so time left at the end of a block when the next episode does not fit is wasted. An episode may
be watched only if it ends at or before its show's leaving time; once a show has left, its
remaining episodes are unwatched and watching moves on to the next show, in the same block if
time is left. An episode counts for the day it ends on.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from contract import Block, Episode, Outcome, Show, Watchlist, Week
from plugin.clock import ClockError, day_minutes, day_text, days_between, minutes_of, stamp_text


class RuleError(ValueError):
    """A watchlist or free-time file that does not follow the format."""


@dataclass(frozen=True)
class Watch:
    show: str
    episode: int
    end: int


@dataclass(frozen=True)
class Plan:
    days: list[tuple[str, list[Watch]]]
    shows: list[tuple[str, Outcome, int | None, list[int]]]


def read_watchlist_data(data) -> Watchlist:
    """The ``Watchlist`` a parsed watchlist file states, or raise ``RuleError``."""
    if not isinstance(data, dict) or not isinstance(data.get("shows"), list) or not data["shows"]:
        raise RuleError("a watchlist holds a shows list with at least one show")
    titles, shows = set(), []
    for entry in data["shows"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("title"), str) or not entry["title"].strip():
            raise RuleError("every show has a title")
        title = entry["title"]
        if title in titles:
            raise RuleError(f"show {title!r} is listed twice")
        titles.add(title)
        episodes = entry.get("episodes")
        if not isinstance(episodes, list) or not episodes:
            raise RuleError(f"{title}: a show has at least one episode")
        numbers, made = set(), []
        for item in episodes:
            if not isinstance(item, dict):
                raise RuleError(f"{title}: every episode is an object")
            number, minutes = item.get("number"), item.get("minutes")
            for name, value in (("number", number), ("minutes", minutes)):
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    raise RuleError(f"{title}: every episode's {name} is a whole number above 0, not {value!r}")
            if number in numbers:
                raise RuleError(f"{title}: episode {number} is listed twice")
            numbers.add(number)
            made.append(Episode(number=number, minutes=minutes))
        leaves = entry.get("leaves")
        if leaves is not None:
            try:
                minutes_of(leaves, f"{title}: leaves")
            except ClockError as error:
                raise RuleError(str(error)) from error
        shows.append(Show(title=title, leaves=leaves, episodes=made))
    return Watchlist(shows=shows)


def read_week_data(data) -> Week:
    """The ``Week`` a parsed free-time file states, or raise ``RuleError``."""
    if not isinstance(data, dict):
        raise RuleError("a free-time file is a JSON object")
    try:
        first = day_minutes(data.get("first_day"), "first_day")
        last = day_minutes(data.get("last_day"), "last_day")
    except ClockError as error:
        raise RuleError(str(error)) from error
    if last < first:
        raise RuleError("last_day is before first_day")
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        raise RuleError("a free-time file holds a blocks list")
    closes = last + 24 * 60 - 1  # the week's last minute: a block may not run past last_day 23:59
    made, previous = [], None
    for position, entry in enumerate(blocks, 1):
        if not isinstance(entry, dict):
            raise RuleError(f"block {position} is not an object")
        try:
            start = minutes_of(entry.get("start"), f"block {position}: start")
            end = minutes_of(entry.get("end"), f"block {position}: end")
        except ClockError as error:
            raise RuleError(str(error)) from error
        if end <= start:
            raise RuleError(f"block {position} ends at or before it starts")
        if start < first or end > closes:
            raise RuleError(f"block {position} runs outside {data['first_day']} to {data['last_day']} 23:59")
        if previous is not None and start < previous:
            raise RuleError(f"block {position} starts before block {position - 1} ends: blocks never overlap")
        previous = end
        made.append(Block(start=entry["start"], end=entry["end"]))
    return Week(first_day=data["first_day"], last_day=data["last_day"], blocks=made)


def plan(watchlist: Watchlist, week: Week) -> Plan:
    """The one schedule the rules give for this watchlist and this week."""
    blocks = [(minutes_of(block.start, "start"), minutes_of(block.end, "end")) for block in week.blocks]
    shows = watchlist.shows
    watched: list[Watch] = []
    # outcome per show, by index: (Outcome, when it finished, the episodes never watched)
    finished_at: dict[int, int] = {}
    left: set[int] = set()
    index, episode = 0, 0

    for start, end in blocks:
        now = start
        while index < len(shows):
            show = shows[index]
            if episode >= len(show.episodes):  # every episode watched
                index, episode = index + 1, 0
                continue
            leaves = None if show.leaves is None else minutes_of(show.leaves, "leaves")
            finish = now + show.episodes[episode].minutes
            # The leaving time is checked first, and on its own: a show whose next episode would
            # end after it leaves is done now, whatever the block allows, and the next show takes
            # the rest of this block. Only then does the block decide (rule 2).
            if leaves is not None and finish > leaves:
                left.add(index)
                index, episode = index + 1, 0
                continue
            if finish > end:  # it does not fit: the rest of this block is wasted
                break
            watched.append(Watch(show=show.title, episode=show.episodes[episode].number, end=finish))
            now, episode = finish, episode + 1
            if episode == len(show.episodes):
                finished_at[index] = finish
                index, episode = index + 1, 0
    closes = blocks[-1][1] if blocks else day_minutes(week.first_day, "first_day")

    days = {day: [] for day in days_between(day_minutes(week.first_day, "first_day"), day_minutes(week.last_day, "last_day"))}
    for watch in watched:
        days.setdefault(day_text(watch.end), []).append(watch)
    seen = {(watch.show, watch.episode) for watch in watched}
    outcomes = []
    for position, show in enumerate(shows):
        unwatched = [item.number for item in show.episodes if (show.title, item.number) not in seen]
        if not unwatched:
            outcomes.append((show.title, Outcome.FINISHED, finished_at[position], []))
        elif position in left or (show.leaves is not None and minutes_of(show.leaves, "leaves") <= closes):
            outcomes.append((show.title, Outcome.LEFT, None, unwatched))
        else:
            outcomes.append((show.title, Outcome.OUT_OF_TIME, None, unwatched))
    return Plan(days=sorted(days.items()), shows=outcomes)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sources_sha256(watchlist_text: str, free_time_text: str) -> str:
    return sha256_text(f"{sha256_text(watchlist_text)}:{sha256_text(free_time_text)}")


def inside(workspace: Path, name: str) -> Path:
    """The path ``name`` names inside ``workspace``; it may not leave it."""
    relative = Path(name)
    root = Path(workspace).resolve()
    path = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(root) or path == root:
        raise RuleError(f"{name!r} must name a file inside the workspace")
    return path


def read_text(workspace: Path, name: str) -> str:
    path = inside(workspace, name)
    if not path.is_file():
        raise RuleError(f"no file at {name}")
    return path.read_text(encoding="utf-8")


def load_sources(workspace: Path, watchlist_name: str, free_time_name: str) -> tuple[Watchlist, Week, str]:
    """The watchlist, the week and the hash of both files."""
    watchlist_text = read_text(workspace, watchlist_name)
    free_time_text = read_text(workspace, free_time_name)
    try:
        watchlist = read_watchlist_data(json.loads(watchlist_text))
        week = read_week_data(json.loads(free_time_text))
    except json.JSONDecodeError as error:
        raise RuleError(f"not JSON: {error}") from error
    return watchlist, week, sources_sha256(watchlist_text, free_time_text)


def stamp(minutes: int) -> str:
    return stamp_text(minutes)
