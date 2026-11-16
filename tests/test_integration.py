"""Load House OS into a real HA test instance and exercise it."""

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.house_os.const import DOMAIN, EVENT_CREW_ARRIVED, EVENT_CREW_LEFT

CAMS = ["binary_sensor.lawn_person_detected", "binary_sensor.patio_person_detected"]
OPTS = {
    "crew_day": "fri", "crew_sensors": CAMS, "day_start_hour": 7, "day_end_hour": 18,
    "min_visit_minutes": 20, "gap_minutes": 20, "battery_threshold": 20,
}


async def _setup(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=OPTS, title="House OS")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_room_rollup(hass: HomeAssistant) -> None:
    areas = ar.async_get(hass)
    kitchen = areas.async_create("Kitchen")
    areas.async_create("Garage")
    other = MockConfigEntry(domain="aqara")
    other.add_to_hass(hass)
    devs, ents = dr.async_get(hass), er.async_get(hass)

    # A leak sensor at 0% battery and an offline lock, both in the kitchen.
    leak = devs.async_get_or_create(config_entry_id=other.entry_id, identifiers={("aqara", "leak")}, name="Sink leak")
    devs.async_update_device(leak.id, area_id=kitchen.id)
    b = ents.async_get_or_create("sensor", "aqara", "leak_batt", device_id=leak.id, config_entry=other)
    hass.states.async_set(b.entity_id, "0", {"device_class": "battery"})
    lock = devs.async_get_or_create(config_entry_id=other.entry_id, identifiers={("aqara", "lock")}, name="Kitchen lock")
    devs.async_update_device(lock.id, area_id=kitchen.id)
    l = ents.async_get_or_create("lock", "aqara", "lock1", device_id=lock.id, config_entry=other)
    u = ents.async_get_or_create("update", "aqara", "lock1_fw", device_id=lock.id, config_entry=other)
    hass.states.async_set(l.entity_id, "unavailable")
    hass.states.async_set(u.entity_id, "off")  # update entities don't count

    await _setup(hass)
    kit = hass.states.get("sensor.house_os_kitchen_attention")
    assert kit is not None, [s.entity_id for s in hass.states.async_all("sensor")]
    assert kit.state == "2"
    assert kit.attributes["offline_devices"] == ["Kitchen lock"]
    assert kit.attributes["low_batteries"] == [{"name": "Sink leak", "level": 0}]
    assert hass.states.get("sensor.house_os_garage_attention").state == "0"
    assert hass.states.get("sensor.house_os_attention").state == "2"
    # the room sensor's device sits in the room, so per-room views pick it up
    ent = ents.async_get("sensor.house_os_kitchen_attention")
    assert devs.async_get(ent.device_id).area_id == kitchen.id


async def test_crew_visit(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await hass.config.async_set_time_zone("America/Los_Angeles")
    for c in CAMS:
        hass.states.async_set(c, "off")
    freezer.move_to(dt_util.as_utc(datetime(2026, 11, 13, 9, 0, tzinfo=dt_util.get_default_time_zone())))
    await _setup(hass)
    arrived, left = [], []
    hass.bus.async_listen(EVENT_CREW_ARRIVED, lambda e: arrived.append(e))
    hass.bus.async_listen(EVENT_CREW_LEFT, lambda e: left.append(e))

    assert hass.states.get("binary_sensor.house_os_garden_crew_on_site").state == "off"
    assert hass.states.get("sensor.house_os_garden_crew_next_visit").state == "2026-11-13"
    for i in range(6):  # detections every 5 min for 25 min
        cam = CAMS[i % 2]
        hass.states.async_set(cam, "on"); await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=5)); hass.states.async_set(cam, "off"); await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.house_os_garden_crew_on_site").state == "on"
    assert len(arrived) == 1

    freezer.tick(timedelta(minutes=30)); async_fire_time_changed(hass); await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.house_os_garden_crew_on_site").state == "off"
    assert len(left) == 1 and left[0].data["minutes"] == 25
    arr = hass.states.get("sensor.house_os_garden_crew_last_arrival")
    assert arr.state.startswith("2026-11-13T17:00")  # 9:00 PT in UTC
    assert hass.states.get("sensor.house_os_garden_crew_last_visit_length").state == "25"
    assert len(arr.attributes["recent_visits"]) == 1


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    res = await hass.config_entries.options.async_configure(flow["flow_id"], {**OPTS, "crew_day": "wed", "day_end_hour": 5})
    assert res["errors"] == {"day_end_hour": "end_before_start"}
    res = await hass.config_entries.options.async_configure(flow["flow_id"], {**OPTS, "crew_day": "wed"})
    assert res["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.runtime_data.crew.weekday == 2
