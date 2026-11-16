"""Shared device info."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN


def house_device(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="House OS",
        entry_type=DeviceEntryType.SERVICE,
    )


def area_device(entry_id: str, area_id: str, area_name: str) -> DeviceInfo:
    # suggested_area places the device, and so its sensor, in the room:
    # that's what makes it show up per room in NeonPlan and area dashboards.
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{area_id}")},
        name=f"House OS {area_name}",
        entry_type=DeviceEntryType.SERVICE,
        suggested_area=area_name,
        via_device=(DOMAIN, entry_id),
    )
