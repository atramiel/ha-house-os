"""Garden crew tracker: turns camera person detections into crew visits."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    BACKFILL_DAYS,
    CONF_CREW_DAY,
    CONF_CREW_SENSORS,
    CONF_DAY_END,
    CONF_DAY_START,
    CONF_GAP_MINUTES,
    CONF_MIN_MINUTES,
    DEFAULT_DAY_END,
    DEFAULT_DAY_START,
    DEFAULT_GAP_MINUTES,
    DEFAULT_MIN_MINUTES,
    DOMAIN,
    EVENT_CREW_ARRIVED,
    EVENT_CREW_LEFT,
    MAX_STORED_VISITS,
    SIGNAL_CREW_UPDATED,
    WEEKDAYS,
)
from .visits import Visit, cluster, in_daytime, next_crew_date

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


def _cam_name(entity_id: str) -> str:
    return entity_id.split(".", 1)[1].removesuffix("_person_detected").replace("_", " ")


class CrewTracker:
    """Tracks the weekly garden crew from person-detection binary sensors."""

    def __init__(self, hass: HomeAssistant, entry_id: str, options: dict[str, Any]) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.sensors: list[str] = list(options.get(CONF_CREW_SENSORS, []))
        self.weekday: int = WEEKDAYS.index(options.get(CONF_CREW_DAY, "fri"))
        self.start_hour: int = int(options.get(CONF_DAY_START, DEFAULT_DAY_START))
        self.end_hour: int = int(options.get(CONF_DAY_END, DEFAULT_DAY_END))
        self.min_len = timedelta(minutes=int(options.get(CONF_MIN_MINUTES, DEFAULT_MIN_MINUTES)))
        self.gap = timedelta(minutes=int(options.get(CONF_GAP_MINUTES, DEFAULT_GAP_MINUTES)))
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.crew")
        self.visits: list[dict[str, Any]] = []
        self.current: Visit | None = None
        self.on_site = False
        self._unsubs: list[CALLBACK_TYPE] = []
        self._close_timer: CALLBACK_TYPE | None = None

    # ---- lifecycle -------------------------------------------------------
    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self.visits = data.get("visits", [])
        await self._async_backfill()
        if self.sensors:
            self._unsubs.append(
                async_track_state_change_event(self.hass, self.sensors, self._on_state)
            )

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._close_timer:
            self._close_timer()
            self._close_timer = None

    # ---- derived values for entities --------------------------------------
    @property
    def last_visit(self) -> dict[str, Any] | None:
        return self.visits[0] if self.visits else None

    @property
    def next_expected(self) -> datetime:
        now = dt_util.now()
        last = self.last_visit
        visited_today = bool(
            self.on_site
            or (last and dt_util.parse_datetime(last["start"]).date() == now.date())
        )
        return next_crew_date(now, self.weekday, visited_today)

    # ---- detection handling ----------------------------------------------
    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        if new is None or new.state != STATE_ON:
            return
        t = dt_util.as_local(new.last_changed)
        if not in_daytime(t, self.start_hour, self.end_hour):
            return
        cam = _cam_name(new.entity_id)
        cur = self.current
        if cur is not None and t - cur.end <= self.gap and t.date() == cur.start.date():
            cur.end = t
            cur.cameras.add(cam)
            cur.detections += 1
        else:
            if cur is not None:
                self._close_current()
            self.current = cur = Visit(start=t, end=t, cameras={cam}, detections=1)

        if (
            not self.on_site
            and cur.start.weekday() == self.weekday
            and cur.end - cur.start >= self.min_len
        ):
            self.on_site = True
            self.hass.bus.async_fire(
                EVENT_CREW_ARRIVED,
                {"arrived": cur.start.isoformat(), "cameras": sorted(cur.cameras)},
            )
        self._schedule_close()
        self._notify()

    def _schedule_close(self) -> None:
        if self._close_timer:
            self._close_timer()
        self._close_timer = async_call_later(
            self.hass, self.gap.total_seconds() + 5, self._on_close_timer
        )

    @callback
    def _on_close_timer(self, _now: datetime) -> None:
        self._close_timer = None
        self._close_current()
        self._notify()

    @callback
    def _close_current(self) -> None:
        cur, self.current = self.current, None
        was_on_site, self.on_site = self.on_site, False
        if cur is None or not was_on_site:
            return
        self._record(cur)
        self.hass.bus.async_fire(EVENT_CREW_LEFT, cur.as_dict())

    def _record(self, visit: Visit) -> bool:
        keys = {v["key"] for v in self.visits}
        if visit.key() in keys:
            return False
        self.visits.insert(0, {"key": visit.key(), **visit.as_dict()})
        self.visits.sort(key=lambda v: v["start"], reverse=True)
        del self.visits[MAX_STORED_VISITS:]
        self._store.async_delay_save(lambda: {"visits": self.visits}, 5)
        return True

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_CREW_UPDATED.format(self.entry_id))

    # ---- history backfill -------------------------------------------------
    async def _async_backfill(self) -> None:
        """Rebuild recent crew visits from the recorder so sensors aren't empty."""
        if not self.sensors or "recorder" not in self.hass.config.components:
            return
        from homeassistant.components.recorder import get_instance, history  # noqa: PLC0415

        start = dt_util.utcnow() - timedelta(days=BACKFILL_DAYS)
        try:
            states = await get_instance(self.hass).async_add_executor_job(
                lambda: history.get_significant_states(
                    self.hass,
                    start,
                    None,
                    self.sensors,
                    include_start_time_state=False,
                    significant_changes_only=True,
                    minimal_response=True,
                    no_attributes=True,
                )
            )
        except Exception:  # noqa: BLE001 - backfill is best effort
            _LOGGER.warning("Couldn't read camera history; crew visits start from now")
            return
        detections: list[tuple[datetime, str]] = []
        for entity_id, rows in states.items():
            cam = _cam_name(entity_id)
            for row in rows:
                state = row.state if hasattr(row, "state") else row.get("state")
                changed = row.last_changed if hasattr(row, "last_changed") else row.get("last_changed")
                if state != STATE_ON or changed is None:
                    continue
                if isinstance(changed, str):
                    changed = dt_util.parse_datetime(changed)
                detections.append((dt_util.as_local(changed), cam))
        today = dt_util.now().date()
        added = 0
        for visit in cluster(
            detections,
            gap=self.gap,
            min_len=self.min_len,
            start_hour=self.start_hour,
            end_hour=self.end_hour,
            weekday=self.weekday,
        ):
            # Leave a visit that may still be running to the live tracker.
            if visit.start.date() == today and dt_util.now() - visit.end < self.gap:
                continue
            added += self._record(visit)
        _LOGGER.debug("Backfilled %s crew visits", added)
