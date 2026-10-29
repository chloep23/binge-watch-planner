"""Local date-times as minutes, from integers alone.

A verifier may not import ``datetime`` or ``calendar``, so this is the calendar: the
days-from-civil algorithm, which turns a proleptic Gregorian date into a day number and back
with integer arithmetic only, leap years and century rules included. The plugin does the same
work with ``datetime`` (``plugin/clock.py``); the two are checked against each other over
thousands of dates, so a mistake here cannot hide behind the same mistake there.

A stamp is ``YYYY-MM-DD HH:MM`` and a day is ``YYYY-MM-DD``, both local and without time zones.
Midnight opens a day: an instant at 00:00 belongs to the day beginning, not the one ending.
"""

import re

STAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})")
DAY = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
MINUTES_A_DAY = 24 * 60


def days_from_civil(year, month, day):
    """The day number of a Gregorian date, 1970-01-01 being 0."""
    year -= month <= 2
    era = (year if year >= 0 else year - 399) // 400
    year_of_era = year - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


def civil_from_days(number):
    """The Gregorian date of a day number: the inverse of :func:`days_from_civil`."""
    number += 719468
    era = (number if number >= 0 else number - 146096) // 146097
    day_of_era = number - era * 146097
    year_of_era = (day_of_era - day_of_era // 1460 + day_of_era // 36524 - day_of_era // 146096) // 365
    year = year_of_era + era * 400
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    months = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * months + 2) // 5 + 1
    month = months + (3 if months < 10 else -9)
    return year + (month <= 2), month, day


def leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def real_date(year, month, day):
    """Whether the three numbers name a day that exists."""
    if not 1 <= month <= 12 or day < 1:
        return False
    lengths = (31, 29 if leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return day <= lengths[month - 1]


def minutes_of(text):
    """The stamp ``text`` as minutes from the epoch, or None when it is not a stamp."""
    found = STAMP.fullmatch(text) if isinstance(text, str) else None
    if not found:
        return None
    year, month, day, hour, minute = (int(part) for part in found.groups())
    if hour > 23 or minute > 59 or not real_date(year, month, day):
        return None
    return days_from_civil(year, month, day) * MINUTES_A_DAY + hour * 60 + minute


def day_minutes(text):
    """The day ``text`` as the minutes of its first instant, or None when it is not a day."""
    return minutes_of(f"{text} 00:00") if isinstance(text, str) and DAY.fullmatch(text) else None


def stamp_text(minutes):
    year, month, day = civil_from_days(minutes // MINUTES_A_DAY)
    rest = minutes % MINUTES_A_DAY
    return f"{year:04d}-{month:02d}-{day:02d} {rest // 60:02d}:{rest % 60:02d}"


def day_text(minutes):
    """The day the instant falls on; midnight belongs to the day it opens."""
    year, month, day = civil_from_days(minutes // MINUTES_A_DAY)
    return f"{year:04d}-{month:02d}-{day:02d}"


def days_between(first, last):
    """Every day from the day of ``first`` to the day of ``last``, inclusive."""
    return [day_text(number * MINUTES_A_DAY) for number in range(first // MINUTES_A_DAY, last // MINUTES_A_DAY + 1)]
