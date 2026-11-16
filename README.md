# House OS for Home Assistant

The glue for a house-wide "what needs doing" view. It sits next to
[Maintenance Supporter](https://github.com/iluebbe/maintenance_supporter)
(recurring jobs) and [Mail and Packages](https://github.com/moralmunky/Home-Assistant-Mail-And-Packages)
(deliveries) and adds the two things they don't do:

1. **Garden crew visits** from your cameras' person detections.
2. **A per-room "Attention" count**: maintenance due, devices offline and batteries low,
   placed in each room so area dashboards and NeonPlan 3D show it in that room.

## Entities

| Entity | What it is |
|---|---|
| `binary_sensor.house_os_garden_crew_on_site` | On while the crew is in the yard on crew day |
| `sensor.house_os_garden_crew_last_arrival` | When the last (or current) visit started; `recent_visits` attribute lists the last 12 |
| `sensor.house_os_garden_crew_last_departure` | When the last visit ended |
| `sensor.house_os_garden_crew_last_visit_length` | Minutes on site last visit |
| `sensor.house_os_garden_crew_next_visit` | Next crew day (today until they've come) |
| `sensor.house_os_attention` | Everything needing attention, house-wide |
| `sensor.house_os_<room>_attention` | One per HA area; attributes list each due job, offline device and low battery |

Events: `house_os_crew_arrived` and `house_os_crew_left` (with start, end, minutes, cameras),
for notifications.

### How a crew visit is detected
Person detections from the sensors you pick, between the daytime hours you set, are grouped
into one visit while no gap between detections is longer than the gap setting. A visit on
crew day that lasts at least the minimum length is a crew visit. On first setup it rebuilds
the last 10 days of visits from the recorder. Visits are kept in HA storage, so the record
outlives the cameras' history.

### What counts toward a room's Attention
- Maintenance Supporter tasks whose problem sensor is on (due soon, overdue or triggered).
- Devices whose every entity is unavailable (update, button, number, select and similar
  helper entities are ignored).
- Battery sensors at or below the threshold.

A device's room is its HA area. Things with no area are listed under `no_room` on
`sensor.house_os_attention`.

## Install
1. HACS / Marketplace → ⋮ → Custom repositories → `https://github.com/atramiel/ha-house-os`,
   type Integration, then install **House OS**. Or copy `custom_components/house_os` into
   `/config/custom_components/`.
2. Restart Home Assistant.
3. Settings → Devices & services → Add integration → **House OS**: pick the crew's day and
   the yard cameras' `*_person_detected` sensors. Everything else can be changed later under
   Configure.

## Development
```bash
pip install pytest-homeassistant-custom-component
pytest
```
