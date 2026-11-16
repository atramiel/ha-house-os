"""Tests for the pure crew-visit clustering."""

from datetime import datetime, timedelta
import importlib.util, pathlib

spec = importlib.util.spec_from_file_location(
    "visits", pathlib.Path(__file__).parents[1] / "custom_components/house_os/visits.py"
)
visits = importlib.util.module_from_spec(spec)
import sys; sys.modules["visits"] = visits
spec.loader.exec_module(visits)

FRI = datetime(2026, 11, 13)  # a Friday
G, M = timedelta(minutes=20), timedelta(minutes=20)


def at(day, h, m, cam="lawn"):
    return (day.replace(hour=h, minute=m), cam)


def run(dets, weekday=4):
    return visits.cluster(dets, gap=G, min_len=M, start_hour=7, end_hour=18, weekday=weekday)


def test_long_visit_with_small_gaps_is_one_visit():
    dets = [at(FRI, 9, m) for m in (0, 15, 30, 45)] + [at(FRI, 10, 5, "patio")]
    (v,) = run(dets)
    assert v.minutes == 65 and v.cameras == {"lawn", "patio"}


def test_gap_splits_and_short_visit_dropped():
    dets = [at(FRI, 9, 0), at(FRI, 9, 10), at(FRI, 11, 0), at(FRI, 11, 15), at(FRI, 11, 30), at(FRI, 11, 45)]
    (v,) = run(dets)
    assert v.start.hour == 11 and v.minutes == 45


def test_night_and_other_days_ignored():
    sat = FRI + timedelta(days=1)
    dets = [at(FRI, 5, m) for m in (0, 10, 20, 30)] + [at(sat, 9, m) for m in (0, 15, 30)]
    assert run(dets) == []
    assert len(run(dets, weekday=None)) == 1


def test_next_crew_date():
    thu = FRI - timedelta(days=1)
    assert visits.next_crew_date(thu, 4, False).date() == FRI.date()
    assert visits.next_crew_date(FRI, 4, False).date() == FRI.date()
    assert visits.next_crew_date(FRI, 4, True).date() == (FRI + timedelta(days=7)).date()
