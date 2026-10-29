"""The calendar, twice. The plugin keeps time with ``datetime``; the verifier may not import it
and does the same work from integers alone. Every check here runs against both, so a mistake in
one cannot hide behind the same mistake in the other."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from plugin import clock
from verifier import civil


@pytest.mark.parametrize("number", list(range(-3000, 22000, 97)))
def test_the_integer_calendar_is_the_standard_library_s(number: int) -> None:
    year, month, day = civil.civil_from_days(number)
    wanted = date(1970, 1, 1) + timedelta(days=number)
    assert (year, month, day) == (wanted.year, wanted.month, wanted.day)
    assert civil.days_from_civil(year, month, day) == number


@pytest.mark.parametrize(
    ("year", "leap"), [(1900, False), (1996, True), (2000, True), (2024, True), (2026, False), (2100, False), (2400, True)]
)
def test_the_century_leap_rules(year: int, leap: bool) -> None:
    assert civil.leap(year) is leap
    assert civil.real_date(year, 2, 29) is leap


@pytest.mark.parametrize(
    "stamp",
    ["2026-03-02 19:00", "2026-03-05 00:00", "2024-02-29 23:59", "1970-01-01 00:00", "2027-12-31 23:59"],
)
def test_both_clocks_agree_on_a_stamp(stamp: str) -> None:
    assert civil.minutes_of(stamp) == clock.minutes_of(stamp, "stamp")
    assert civil.stamp_text(civil.minutes_of(stamp)) == stamp
    assert clock.stamp_text(clock.minutes_of(stamp, "stamp")) == stamp


@pytest.mark.parametrize("stamp", ["2026-03-02 24:00", "2026-03-02 19:60", "2026-02-30 19:00", "2026-13-01 19:00", "2026-03-02", "", "x"])
def test_both_clocks_refuse_what_is_not_a_stamp(stamp: str) -> None:
    assert civil.minutes_of(stamp) is None
    with pytest.raises(clock.ClockError):
        clock.minutes_of(stamp, "stamp")


@pytest.mark.parametrize(
    ("stamp", "day"),
    [
        ("2026-03-04 23:59", "2026-03-04"),
        ("2026-03-05 00:00", "2026-03-05"),  # midnight opens the new day
        ("2026-03-05 00:20", "2026-03-05"),
        ("2026-03-05 23:59", "2026-03-05"),
    ],
)
def test_midnight_belongs_to_the_day_it_opens(stamp: str, day: str) -> None:
    assert civil.day_text(civil.minutes_of(stamp)) == day
    assert clock.day_text(clock.minutes_of(stamp, "stamp")) == day


def test_the_days_of_a_week_run_inclusively_across_a_month_end() -> None:
    first, last = civil.day_minutes("2026-02-26"), civil.day_minutes("2026-03-02")
    assert civil.days_between(first, last) == ["2026-02-26", "2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02"]
    assert clock.days_between(clock.day_minutes("2026-02-26", "d"), clock.day_minutes("2026-03-02", "d")) == civil.days_between(first, last)


def test_a_leap_day_is_a_day_like_any_other() -> None:
    assert civil.days_between(civil.day_minutes("2024-02-28"), civil.day_minutes("2024-03-01")) == ["2024-02-28", "2024-02-29", "2024-03-01"]
