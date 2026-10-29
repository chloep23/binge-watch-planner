"""The watching rules, twice: the plugin's simulation and the verifier's own, on made-up weeks
that isolate one rule at a time."""

from __future__ import annotations

import pytest

import verifier.rules as checked
from plugin.clock import stamp_text as plugin_stamp
from plugin.rules import plan, read_watchlist_data, read_week_data


def shows(*entries):
    """(title, leaves, [minutes...]) each -> a watchlist."""
    return {
        "shows": [
            {"title": title, "leaves": leaves, "episodes": [{"number": n, "minutes": m} for n, m in enumerate(mins, 1)]}
            for title, leaves, mins in entries
        ]
    }


def week(*blocks, first="2026-03-02", last="2026-03-02"):
    return {"first_day": first, "last_day": last, "blocks": [{"start": s, "end": e} for s, e in blocks]}


def both(watchlist, free_time):
    """(the days, the shows) from each implementation, as comparable plain values."""
    made = plan(read_watchlist_data(watchlist), read_week_data(free_time))
    mine = (
        [(day, [(w.show, w.episode, plugin_stamp(w.end)) for w in watches]) for day, watches in made.days],
        [(title, outcome.value, None if at is None else plugin_stamp(at), unwatched) for title, outcome, at, unwatched in made.shows],
    )
    parsed_shows, _ = checked.parse_watchlist(watchlist)
    parsed_week, _ = checked.parse_week(free_time)
    days, outcomes = checked.simulate(parsed_shows, parsed_week)
    theirs = (
        [(day, [(t, n, checked.stamp_text(end)) for t, n, end in sorted(w, key=lambda x: x[2])]) for day, w in sorted(days.items())],
        [(t, o, None if a is None else checked.stamp_text(a), u) for t, o, a, u in outcomes],
    )
    assert mine == theirs, "the two simulations disagree"
    return mine


def test_an_episode_fits_only_if_it_ends_at_or_before_the_block_end() -> None:
    days, _ = both(shows(("A", None, [60])), week(("2026-03-02 19:00", "2026-03-02 20:00")))
    assert len(days[0][1]) == 1, "60 minutes in exactly 60 minutes"
    days, _ = both(shows(("A", None, [61])), week(("2026-03-02 19:00", "2026-03-02 20:00")))
    assert days[0][1] == [], "one minute too long"


def test_blocks_never_merge() -> None:
    touching = week(("2026-03-02 19:00", "2026-03-02 19:40"), ("2026-03-02 19:40", "2026-03-02 20:20"))
    days, _ = both(shows(("A", None, [50])), touching)
    assert days[0][1] == [], "50 minutes fits the 80 they would make, and neither of them"
    days, _ = both(shows(("A", None, [40, 40])), touching)
    assert len(days[0][1]) == 2, "one in each"


def test_time_left_when_the_next_episode_does_not_fit_is_wasted() -> None:
    days, _ = both(shows(("A", None, [20, 50])), week(("2026-03-02 19:00", "2026-03-02 20:00")))
    assert [w[1] for w in days[0][1]] == [1], "episode 2 does not fit, and 1 is never skipped for a shorter one"


def test_an_episode_may_end_exactly_at_the_leaving_time() -> None:
    _, outcomes = both(shows(("A", "2026-03-02 20:00", [60])), week(("2026-03-02 19:00", "2026-03-02 22:00")))
    assert outcomes[0][1] == "finished"
    _, outcomes = both(shows(("A", "2026-03-02 19:59", [60])), week(("2026-03-02 19:00", "2026-03-02 22:00")))
    assert outcomes[0][1] == "left" and outcomes[0][3] == [1]


def test_once_a_show_has_left_the_next_one_uses_the_rest_of_the_block() -> None:
    days, outcomes = both(
        shows(("A", "2026-03-02 19:30", [60]), ("B", None, [30])),
        week(("2026-03-02 19:00", "2026-03-02 22:00")),
    )
    assert [(w[0], w[1]) for w in days[0][1]] == [("B", 1)]
    assert outcomes[0][1] == "left" and outcomes[1][1] == "finished"


def test_a_show_is_never_skipped_for_a_later_one_that_would_fit() -> None:
    days, outcomes = both(
        shows(("A", None, [90]), ("B", None, [20])),
        week(("2026-03-02 19:00", "2026-03-02 19:30")),
    )
    assert days[0][1] == [], "B fits, but A comes first and is not finished"
    assert [outcome[1] for outcome in outcomes] == ["out-of-time", "out-of-time"]


def test_the_leaving_check_comes_before_the_block_check() -> None:
    """An episode that would end both after its show leaves and past the block end: rule 4 wins,
    the show is done at once, and the next show gets the rest of the block."""
    days, outcomes = both(
        shows(("A", "2026-03-02 19:30", [90]), ("B", None, [50])),
        week(("2026-03-02 19:00", "2026-03-02 20:00")),
    )
    assert [(w[0], w[1]) for w in days[0][1]] == [("B", 1)]
    assert [(o[0], o[1]) for o in outcomes] == [("A", "left"), ("B", "finished")]


def test_an_episode_that_fits_the_leaving_time_but_not_the_block_waits_for_the_next_block() -> None:
    """The other half: the episode ends before the show leaves, so rule 2 decides and the rest of
    the block is wasted. The show is not abandoned, and it is watched in the next block."""
    days, outcomes = both(
        shows(("A", "2026-03-03 23:00", [50]), ("B", None, [20])),
        week(("2026-03-02 19:00", "2026-03-02 19:40"), ("2026-03-02 20:00", "2026-03-02 21:00"),
             first="2026-03-02", last="2026-03-03"),
    )
    assert [(w[0], w[1], w[2]) for w in days[0][1]] == [("A", 1, "2026-03-02 20:50")], (
        "the first block is wasted and A is watched in the second, not abandoned"
    )
    assert [(o[0], o[1]) for o in outcomes] == [("A", "finished"), ("B", "out-of-time")]


def test_an_episode_counts_for_the_day_it_ends_on() -> None:
    days, _ = both(
        shows(("A", None, [60, 20])),
        week(("2026-03-02 23:00", "2026-03-03 00:30"), first="2026-03-02", last="2026-03-03"),
    )
    assert days[0] == ("2026-03-02", []), "the first episode ends at midnight, which opens 03-03"
    assert [(w[1], w[2]) for w in days[1][1]] == [(1, "2026-03-03 00:00"), (2, "2026-03-03 00:20")]


def test_a_show_that_never_leaves_and_runs_out_of_week_is_out_of_time() -> None:
    _, outcomes = both(shows(("A", None, [60, 60])), week(("2026-03-02 19:00", "2026-03-02 20:00")))
    assert outcomes[0] == ("A", "out-of-time", None, [2])


@pytest.mark.parametrize(
    "broken",
    [
        {"shows": []},
        {"shows": [{"title": "", "episodes": [{"number": 1, "minutes": 10}]}]},
        {"shows": [{"title": "A", "episodes": []}]},
        {"shows": [{"title": "A", "episodes": [{"number": 1, "minutes": 0}]}]},
        {"shows": [{"title": "A", "episodes": [{"number": 1, "minutes": 10}, {"number": 1, "minutes": 10}]}]},
        {"shows": [{"title": "A", "leaves": "nope", "episodes": [{"number": 1, "minutes": 10}]}]},
    ],
)
def test_a_watchlist_that_breaks_the_format_is_refused_by_both(broken: dict) -> None:
    from plugin.rules import RuleError

    found, problem = checked.parse_watchlist(broken)
    assert found is None and problem
    with pytest.raises(RuleError):
        read_watchlist_data(broken)
