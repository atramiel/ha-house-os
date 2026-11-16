"""Pure visit-clustering logic for the garden crew tracker.

No Home Assistant imports, so it can be unit tested on its own.
A visit is a run of person detections where no two consecutive detections
are more than `gap` apart, inside daytime hours, lasting at least `min_len`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Visit:
    start: datetime
    end: datetime
    cameras: set[str] = field(default_factory=set)
    detections: int = 0

    @property
    def minutes(self) -> int:
        return round((self.end - self.start).total_seconds() / 60)

    def key(self) -> str:
        return self.start.strftime("%Y%m%dT%H%M")

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "minutes": self.minutes,
            "cameras": sorted(self.cameras),
        }


def in_daytime(t: datetime, start_hour: int, end_hour: int) -> bool:
    """t must already be local time."""
    return start_hour <= t.hour < end_hour


def cluster(
    detections: list[tuple[datetime, str]],
    *,
    gap: timedelta,
    min_len: timedelta,
    start_hour: int,
    end_hour: int,
    weekday: int | None,
) -> list[Visit]:
    """Group local-time detections into visits.

    weekday: only keep visits that start on this weekday (Monday=0); None keeps all.
    """
    visits: list[Visit] = []
    cur: Visit | None = None
    for t, cam in sorted(detections, key=lambda d: d[0]):
        if not in_daytime(t, start_hour, end_hour):
            continue
        if cur is not None and t - cur.end <= gap and t.date() == cur.start.date():
            cur.end = t
            cur.cameras.add(cam)
            cur.detections += 1
            continue
        if cur is not None:
            visits.append(cur)
        cur = Visit(start=t, end=t, cameras={cam}, detections=1)
    if cur is not None:
        visits.append(cur)
    return [
        v
        for v in visits
        if v.end - v.start >= min_len and (weekday is None or v.start.weekday() == weekday)
    ]


def next_crew_date(today: datetime, weekday: int, visited_today: bool) -> datetime:
    """Next date the crew is expected (today counts until they've come)."""
    days = (weekday - today.weekday()) % 7
    if days == 0 and visited_today:
        days = 7
    return today + timedelta(days=days)
