"""Local date-times, in minutes. The plugin has the standard library's calendar to hand, so this
side of the plugin uses ``datetime``; the verifier, which may not import it, does the same
arithmetic from integers alone (``verifier/civil.py``). The two are checked against each other.

A stamp is ``YYYY-MM-DD HH:MM``, local and with no time zone, and a day is ``YYYY-MM-DD``. Both
become minutes from 1970-01-01 00:00, so every comparison in the rules is an integer one.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

STAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})")
DAY = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
EPOCH = date(1970, 1, 1)
MINUTES_A_DAY = 24 * 60


class ClockError(ValueError):
    """A stamp or a day that is not written the way the format says."""


def minutes_of(text: str, where: str) -> int:
    """The stamp ``text`` as minutes from the epoch."""
    if not isinstance(text, str) or not STAMP.fullmatch(text):
        raise ClockError(f'{where} must be a date and time "YYYY-MM-DD HH:MM", not {text!r}')
    year, month, day, hour, minute = (int(part) for part in STAMP.fullmatch(text).groups())
    if hour > 23 or minute > 59:
        raise ClockError(f"{where} is not a time of day: {text!r}")
    try:
        when = datetime(year, month, day, hour, minute)
    except ValueError as error:
        raise ClockError(f"{where} is not a date: {text!r}") from error
    return int((when - datetime(1970, 1, 1)).total_seconds()) // 60


def day_minutes(text: str, where: str) -> int:
    """The day ``text`` as the minutes of its first instant."""
    if not isinstance(text, str) or not DAY.fullmatch(text):
        raise ClockError(f'{where} must be a day "YYYY-MM-DD", not {text!r}')
    return minutes_of(f"{text} 00:00", where)


def stamp_text(minutes: int) -> str:
    """The minutes back as a stamp."""
    return (datetime(1970, 1, 1) + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")


def day_text(minutes: int) -> str:
    """The day the instant ``minutes`` falls on. Midnight belongs to the day it opens, so an
    episode ending at 00:00 counts for that new day."""
    return (EPOCH + timedelta(days=minutes // MINUTES_A_DAY)).isoformat()


def days_between(first: int, last: int) -> list[str]:
    """Every day from the day of ``first`` to the day of ``last``, inclusive."""
    start, end = first // MINUTES_A_DAY, last // MINUTES_A_DAY
    return [(EPOCH + timedelta(days=offset)).isoformat() for offset in range(start, end + 1)]
