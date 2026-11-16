"""Config and options flow for House OS."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_THRESHOLD,
    CONF_CREW_DAY,
    CONF_CREW_SENSORS,
    CONF_DAY_END,
    CONF_DAY_START,
    CONF_GAP_MINUTES,
    CONF_MIN_MINUTES,
    DEFAULT_BATTERY_THRESHOLD,
    DEFAULT_DAY_END,
    DEFAULT_DAY_START,
    DEFAULT_GAP_MINUTES,
    DEFAULT_MIN_MINUTES,
    DOMAIN,
    WEEKDAYS,
)


def _num(lo: int, hi: int, unit: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=lo, max=hi, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit
        )
    )


def _schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CREW_DAY, default=d.get(CONF_CREW_DAY, "fri")): selector.SelectSelector(
                selector.SelectSelectorConfig(options=WEEKDAYS, translation_key="weekday")
            ),
            vol.Required(CONF_CREW_SENSORS, default=d.get(CONF_CREW_SENSORS, [])): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
            vol.Required(CONF_DAY_START, default=d.get(CONF_DAY_START, DEFAULT_DAY_START)): _num(0, 23, "h"),
            vol.Required(CONF_DAY_END, default=d.get(CONF_DAY_END, DEFAULT_DAY_END)): _num(1, 24, "h"),
            vol.Required(CONF_MIN_MINUTES, default=d.get(CONF_MIN_MINUTES, DEFAULT_MIN_MINUTES)): _num(5, 240, "min"),
            vol.Required(CONF_GAP_MINUTES, default=d.get(CONF_GAP_MINUTES, DEFAULT_GAP_MINUTES)): _num(5, 120, "min"),
            vol.Required(
                CONF_BATTERY_THRESHOLD, default=d.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD)
            ): _num(1, 100, "%"),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    out = dict(user_input)
    for key in (CONF_DAY_START, CONF_DAY_END, CONF_MIN_MINUTES, CONF_GAP_MINUTES, CONF_BATTERY_THRESHOLD):
        out[key] = int(out[key])
    return out


class HouseOsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if int(user_input[CONF_DAY_END]) <= int(user_input[CONF_DAY_START]):
                errors[CONF_DAY_END] = "end_before_start"
            else:
                return self.async_create_entry(title="House OS", data=_clean(user_input))
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HouseOsOptionsFlow()


class HouseOsOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            if int(user_input[CONF_DAY_END]) <= int(user_input[CONF_DAY_START]):
                errors[CONF_DAY_END] = "end_before_start"
            else:
                return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(step_id="init", data_schema=_schema(user_input or current), errors=errors)
