"""Live-adjustable minimum power filter (kW) — e.g. 50 = fast chargers only."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MIN_POWER_KW, CONF_RADIUS_KM, DEFAULT_MIN_POWER_KW
from .device import device_info, entry_suffix
from .localization import t


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([MinPowerNumber(hass, entry)])


class MinPowerNumber(NumberEntity):
    """Minimum power (kW) — stations below this are hidden from the map."""

    _attr_has_entity_name = False
    _attr_native_unit_of_measurement = "kW"
    _attr_native_min_value = 0
    _attr_native_max_value = 350
    _attr_native_step = 10
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:ev-station"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_name = t("min_power_name", hass)
        self._attr_unique_id = f"{entry.entry_id}_min_power_kw"
        self._attr_device_info = device_info(hass, entry)
        # The suggested entity id carries the radius and the entry suffix,
        # like the availability sensor's does: a fixed id is shared by every
        # radius entry, and the radius alone is shared by two entries at
        # different locations with the same radius — Home Assistant resolves
        # either by appending _2 to the second, so an automation copied
        # between entries silently targets the wrong one (see entry_suffix).
        # Applies on first creation only; existing entities keep their id.
        radius = entry.data.get(CONF_RADIUS_KM)
        self.entity_id = f"number.charging_stations_min_power_kw_{round(radius)}km_{entry_suffix(entry)}"

    @property
    def native_value(self) -> float:
        return self._entry.options.get(CONF_MIN_POWER_KW, DEFAULT_MIN_POWER_KW)

    async def async_set_native_value(self, value: float) -> None:
        new_options = {**self._entry.options, CONF_MIN_POWER_KW: value}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
