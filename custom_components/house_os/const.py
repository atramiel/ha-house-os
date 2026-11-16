"""Constants for House OS."""

from __future__ import annotations

DOMAIN = "house_os"

CONF_CREW_DAY = "crew_day"
CONF_CREW_SENSORS = "crew_sensors"
CONF_DAY_START = "day_start_hour"
CONF_DAY_END = "day_end_hour"
CONF_MIN_MINUTES = "min_visit_minutes"
CONF_GAP_MINUTES = "gap_minutes"
CONF_BATTERY_THRESHOLD = "battery_threshold"

DEFAULT_DAY_START = 7
DEFAULT_DAY_END = 18
DEFAULT_MIN_MINUTES = 20
DEFAULT_GAP_MINUTES = 20
DEFAULT_BATTERY_THRESHOLD = 20

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # datetime.weekday() order

EVENT_CREW_ARRIVED = "house_os_crew_arrived"
EVENT_CREW_LEFT = "house_os_crew_left"

SIGNAL_CREW_UPDATED = "house_os_crew_updated_{}"

# Entity domains that never mean "the device is offline" when unavailable.
IGNORED_OFFLINE_DOMAINS = {"update", "button", "number", "select", "event", "image", "time", "text", "scene"}

MAINTENANCE_DOMAIN = "maintenance_supporter"
ROLLUP_INTERVAL_MINUTES = 5
MAX_STORED_VISITS = 200
BACKFILL_DAYS = 10
