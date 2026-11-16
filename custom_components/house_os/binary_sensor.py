"""Crew on-site binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HouseOsConfigEntry
from .const import SIGNAL_CREW_UPDATED
from .entity import house_device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HouseOsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([CrewOnSite(entry)])


class CrewOnSite(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "crew_on_site"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_should_poll = False

    def __init__(self, entry: HouseOsConfigEntry) -> None:
        self._crew = entry.runtime_data.crew
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_crew_on_site"
        self._attr_device_info = house_device(entry.entry_id)

    @property
    def is_on(self) -> bool:
        return self._crew.on_site

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_CREW_UPDATED.format(self._entry_id), self.async_write_ha_state
            )
        )
