"""Per-room attention rollup: due maintenance, offline devices, low batteries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BATTERY_THRESHOLD,
    DEFAULT_BATTERY_THRESHOLD,
    DOMAIN,
    IGNORED_OFFLINE_DOMAINS,
    MAINTENANCE_DOMAIN,
    ROLLUP_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)
NO_AREA = "_none"


@dataclass
class AreaReport:
    maintenance: list[str] = field(default_factory=list)
    offline: list[str] = field(default_factory=list)
    batteries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.maintenance) + len(self.offline) + len(self.batteries)

    def as_attributes(self) -> dict[str, Any]:
        return {
            "maintenance_due": self.maintenance,
            "offline_devices": self.offline,
            "low_batteries": self.batteries,
        }


class RollupCoordinator(DataUpdateCoordinator[dict[str, AreaReport]]):
    """Recomputes every few minutes; cheap, reads only the state machine and registries."""

    def __init__(self, hass: HomeAssistant, entry, options: dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} rollup",
            update_interval=timedelta(minutes=ROLLUP_INTERVAL_MINUTES),
        )
        self.threshold = int(options.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD))

    async def _async_update_data(self) -> dict[str, AreaReport]:
        hass = self.hass
        ents = er.async_get(hass)
        devs = dr.async_get(hass)
        areas = ar.async_get(hass)
        reports: dict[str, AreaReport] = defaultdict(AreaReport)

        def area_of(entry: er.RegistryEntry) -> str:
            if entry.area_id:
                return entry.area_id
            if entry.device_id and (dev := devs.async_get(entry.device_id)) and dev.area_id:
                return dev.area_id
            return NO_AREA

        def dev_name(device_id: str | None, fallback: str) -> str:
            if device_id and (dev := devs.async_get(device_id)):
                return dev.name_by_user or dev.name or fallback
            return fallback

        by_device: dict[str, list[er.RegistryEntry]] = defaultdict(list)
        for entry in ents.entities.values():
            if entry.disabled_by or entry.platform == DOMAIN:
                continue
            state = hass.states.get(entry.entity_id)
            if state is None:
                continue
            if entry.device_id:
                by_device[entry.device_id].append(entry)

            # Due or overdue maintenance: Maintenance Supporter's problem binary sensors.
            if (
                entry.platform == MAINTENANCE_DOMAIN
                and entry.domain == "binary_sensor"
                and state.state == STATE_ON
            ):
                reports[area_of(entry)].maintenance.append(
                    state.attributes.get("friendly_name", entry.entity_id)
                )
                continue

            # Low batteries (skip our own and maintenance entities).
            if (
                entry.domain == "sensor"
                and state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.BATTERY
            ):
                try:
                    level = float(state.state)
                except ValueError:
                    continue
                if 0 <= level <= self.threshold:
                    reports[area_of(entry)].batteries.append(
                        {
                            "name": dev_name(entry.device_id, state.name),
                            "level": round(level),
                        }
                    )

        # Offline devices: every meaningful entity on the device is unavailable.
        for device_id, entries in by_device.items():
            meaningful = [e for e in entries if e.domain not in IGNORED_OFFLINE_DOMAINS]
            if not meaningful:
                continue
            if all(
                (s := hass.states.get(e.entity_id)) is not None and s.state == STATE_UNAVAILABLE
                for e in meaningful
            ):
                dev = devs.async_get(device_id)
                if dev is None or dev.disabled_by:
                    continue
                area_id = dev.area_id or NO_AREA
                reports[area_id].offline.append(dev.name_by_user or dev.name or device_id)

        # Make sure every area has a (possibly empty) report so its sensor reads 0.
        for area in areas.async_list_areas():
            reports.setdefault(area.id, AreaReport())
        return dict(reports)
