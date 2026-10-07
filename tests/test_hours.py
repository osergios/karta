"""Schedule parsing, holidays and the schedule API."""
from datetime import date, datetime

import pytest
from conftest import set_schedule

from app import hours

DAY = date(2026, 10, 6)


def paid_hours(text: str) -> float:
    """Paid hours of a schedule line, the way the report counts them."""
    sp = hours.parse_span(text)
    segs = tuple((datetime.combine(DAY, hours._t(a)), datetime.combine(DAY, hours._t(b))) for a, b in sp.segments)
    return hours.scheduled_seconds(hours.Sched(segs[0][0], segs[-1][1], sp.break_min, segs, sp.break_out)) / 3600


def test_simple_day():
    s = hours.parse_span("09:00-17:00")
    assert (s.start, s.end, s.break_min, s.break_out, s.split) == ("09:00", "17:00", 0, False, False)


def test_break_inside_the_hours():
    s = hours.parse_span("10:00-18:30/30")
    assert (s.break_min, s.break_out) == (30, False)
    assert paid_hours("10:00-18:30/30") == 8


def test_break_outside_the_hours():
    s = hours.parse_span("10:00-16:30/+30")
    assert (s.break_min, s.break_out) == (30, True)
    assert paid_hours("10:00-16:30/+30") == 6.5
    assert s.text == "10:00-16:30/+30"


def test_split_shift():
    s = hours.parse_span("10:00-14:00+17:00-21:00")
    assert s.split
    assert s.segments == (("10:00", "14:00"), ("17:00", "21:00"))
    assert paid_hours("10:00-14:00+17:00-21:00") == 8


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_means_day_off(text):
    assert hours.parse_span(text) is None


@pytest.mark.parametrize("text", ["17:00-09:00", "9-17", "10:00-14:00+13:00-18:00", "25:00-26:00", "abc"])
def test_bad_schedules_are_rejected(text):
    with pytest.raises(ValueError):
        hours.parse_span(text)


@pytest.mark.parametrize("year, easter", [(2025, date(2025, 4, 20)), (2026, date(2026, 4, 12)),
                                          (2027, date(2027, 5, 2))])
def test_orthodox_easter(year, easter):
    assert hours.orthodox_easter(year) == easter


def test_greek_public_holidays(client):
    days = {h["date"]: h for h in hours.holidays(2026)}
    for d in (date(2026, 1, 1), date(2026, 3, 25), date(2026, 4, 13), date(2026, 10, 28), date(2026, 12, 25)):
        assert d in days and days[d]["closed"]
    assert days[date(2026, 2, 23)]["name"] == "Καθαρά Δευτέρα"
    assert days[date(2026, 4, 10)]["closed"] is False          # Μεγάλη Παρασκευή: open by default


def test_schedule_api_saves_and_validates(client, admin, clock, employee):
    set_schedule(client, employee, {"1": "09:00-17:00/30", "3": "10:00-14:00+17:00-21:00"})
    sched = hours.schedule_for(employee, date(2026, 10, 6))        # Tuesday
    assert sched.label() == "09:00–17:00 · διάλ. 30′"
    assert sched.start == datetime(2026, 10, 6, 9, 0)
    assert hours.schedule_for(employee, date(2026, 10, 5)) is None  # Monday: day off

    r = client.post(f"/admin/api/schedules/{employee}", json={"days": {"1": "17:00-09:00"}})
    assert r.status_code == 400


def test_schedule_history_keeps_the_old_schedule_for_past_days(client, admin, clock, employee):
    set_schedule(client, employee, {"1": "09:00-17:00"}, valid_from="2026-09-01")
    set_schedule(client, employee, {"1": "10:00-18:00"}, valid_from="2026-10-06")
    assert f"{hours.schedule_for(employee, date(2026, 9, 29)).start:%H:%M}" == "09:00"
    assert f"{hours.schedule_for(employee, date(2026, 10, 6)).start:%H:%M}" == "10:00"
