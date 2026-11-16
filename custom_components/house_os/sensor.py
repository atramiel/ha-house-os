"""House OS sensors."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import HouseOsConfigEntry
from .const import SIGNAL_CREW_UPDATED
from .entity import area_device, house_device
from .rollup import NO_AREA, AreaReport, RollupCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HouseOsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    entities: list[SensorEntity] = [
        CrewArrivalSensor(entry),
        CrewDepartureSensor(entry),
        CrewDurationSensor(entry),
        CrewNextSensor(entry),
        HouseAttentionSensor(data.rollup, entry.entry_id),
    ]
    for area in ar.async_get(hass).async_list_areas():
        entities.append(AreaAttentionSensor(data.rollup, entry.entry_id, area.id, area.name))
    async_add_entities(entities)

    known = {area.id for area in ar.async_get(hass).async_list_areas()}

    @callback
    def _areas_changed(_event) -> None:
        # Add a sensor for any newly created room without a reload.
        new = [
            AreaAttentionSensor(data.rollup, entry.entry_id, a.id, a.name)
            for a in ar.async_get(hass).async_list_areas()
            if a.id not in known
        ]
        known.update(e.area_id for e in new)
        if new:
            async_add_entities(new)

    entry.async_on_unload(hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, _areas_changed))


# ---- crew ------------------------------------------------------------------
class _CrewSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: HouseOsConfigEntry) -> None:
        self._crew = entry.runtime_data.crew
        self._attr_device_info = house_device(entry.entry_id)
        self._attr_unique_id = f"{entry.entry_id}_{self.key}"
        self._entry_id = entry.entry_id

    key = ""

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_CREW_UPDATED.format(self._entry_id), self.async_write_ha_state
            )
        )


class CrewArrivalSensor(_CrewSensor):
    key = "crew_last_arrival"
    _attr_translation_key = "crew_last_arrival"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:account-hard-hat"

    @property
    def native_value(self) -> datetime | None:
        if self._crew.on_site and self._crew.current:
            return self._crew.current.start
        last = self._crew.last_visit
        return dt_util.parse_datetime(last["start"]) if last else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "on_site": self._crew.on_site,
            "recent_visits": [
                {k: v for k, v in visit.items() if k != "key"} for visit in self._crew.visits[:12]
            ],
        }


class CrewDepartureSensor(_CrewSensor):
    key = "crew_last_departure"
    _attr_translation_key = "crew_last_departure"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:exit-run"

    @property
    def native_value(self) -> datetime | None:
        last = self._crew.last_visit
        return dt_util.parse_datetime(last["end"]) if last else None


class CrewDurationSensor(_CrewSensor):
    key = "crew_last_visit_length"
    _attr_translation_key = "crew_last_visit_length"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        last = self._crew.last_visit
        return last["minutes"] if last else None


class CrewNextSensor(_CrewSensor):
    key = "crew_next_visit"
    _attr_translation_key = "crew_next_visit"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-clock"
    _attr_should_poll = True  # rolls over at midnight

    @property
    def native_value(self) -> date:
        return self._crew.next_expected.date()


# ---- rollups -----------------------------------------------------------------
class HouseAttentionSensor(CoordinatorEntity[RollupCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "house_attention"
    _attr_icon = "mdi:home-alert"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RollupCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_house_attention"
        self._attr_device_info = house_device(entry_id)

    def _merged(self) -> AreaReport:
        out = AreaReport()
        for area_id, rep in (self.coordinator.data or {}).items():
            out.maintenance += rep.maintenance
            out.batteries += rep.batteries
            # Devices with no room are mostly network clients (phones, laptops
            # that are away); they stay listed under no_room but don't count.
            if area_id != NO_AREA:
                out.offline += rep.offline
        return out

    @property
    def native_value(self) -> int:
        return self._merged().total

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        merged = self._merged()
        unassigned = (self.coordinator.data or {}).get(NO_AREA, AreaReport())
        return {
            "maintenance_due": len(merged.maintenance),
            "offline_devices": len(merged.offline),
            "low_batteries": len(merged.batteries),
            "no_room": unassigned.as_attributes(),
        }


class AreaAttentionSensor(CoordinatorEntity[RollupCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "area_attention"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: RollupCoordinator, entry_id: str, area_id: str, area_name: str
    ) -> None:
        super().__init__(coordinator)
        self.area_id = area_id
        self._attr_unique_id = f"{entry_id}_attention_{area_id}"
        self._attr_device_info = area_device(entry_id, area_id, area_name)

    def _report(self) -> AreaReport:
        return (self.coordinator.data or {}).get(self.area_id, AreaReport())

    @property
    def native_value(self) -> int:
        return self._report().total

    @property
    def icon(self) -> str:
        return "mdi:home-alert" if self._report().total else "mdi:home-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._report().as_attributes()
