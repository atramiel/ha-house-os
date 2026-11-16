"""House OS: garden crew visits and per-room attention for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .crew import CrewTracker
from .rollup import RollupCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass
class HouseOsData:
    crew: CrewTracker
    rollup: RollupCoordinator


type HouseOsConfigEntry = ConfigEntry[HouseOsData]


async def async_setup_entry(hass: HomeAssistant, entry: HouseOsConfigEntry) -> bool:
    options = {**entry.data, **entry.options}
    crew = CrewTracker(hass, entry.entry_id, options)
    await crew.async_start()
    rollup = RollupCoordinator(hass, entry, options)
    await rollup.async_config_entry_first_refresh()
    entry.runtime_data = HouseOsData(crew=crew, rollup=rollup)
    entry.async_on_unload(crew.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: HouseOsConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HouseOsConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
