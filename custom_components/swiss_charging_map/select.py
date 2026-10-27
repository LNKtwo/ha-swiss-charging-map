"""Live-adjustable selection filters: plug type, status, operator.

Plug type / operator options are discovered dynamically from the stations
currently found within the radius (no hardcoded list) — automatically
adapts if new operators or plug types appear. Only the "all" sentinel and
the two status values are localized; raw plug type / operator strings from
the source data are shown as-is regardless of the active HA language.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_OPERATOR,
    CONF_PLUG_TYPE,
    CONF_RADIUS_KM,
    CONF_STATUS,
    DOMAIN,
    FILTER_ALL,
    STATUS_AVAILABLE,
    STATUS_OCCUPIED,
)
from .coordinator import IchTankeStromCoordinator
from .device import device_info, entry_suffix
from .localization import t


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: IchTankeStromCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PlugTypeSelect(hass, coordinator, entry),
            StatusSelect(hass, coordinator, entry),
            OperatorSelect(hass, coordinator, entry),
        ]
    )


class _FilterSelect(CoordinatorEntity[IchTankeStromCoordinator], SelectEntity):
    """Base class: stores the selection in the config entry's options.

    The suggested entity ids carry the radius and the entry suffix, like
    the availability sensor's does (number.py explains why). First creation
    only; existing entities keep their id."""

    _attr_has_entity_name = False
    _option_key: str

    def __init__(self, hass: HomeAssistant, coordinator: IchTankeStromCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._hass_ref = hass
        self._entry = entry
        self._attr_device_info = device_info(hass, entry)


class PlugTypeSelect(_FilterSelect):
    """Filter by plug type (e.g. CCS only)."""

    _attr_icon = "mdi:power-plug-outline"
    _option_key = CONF_PLUG_TYPE

    def __init__(self, hass: HomeAssistant, coordinator: IchTankeStromCoordinator, entry: ConfigEntry) -> None:
        super().__init__(hass, coordinator, entry)
        self._attr_name = t("plug_type_name", hass)
        self._attr_unique_id = f"{entry.entry_id}_plug_type"
        radius = entry.data.get(CONF_RADIUS_KM)
        self.entity_id = f"select.charging_stations_plug_type_{round(radius)}km_{entry_suffix(entry)}"

    @property
    def options(self) -> list[str]:
        plug_types = (self.coordinator.data or {}).get("plug_types", [])
        return [t("option_all", self._hass_ref), *plug_types]

    @property
    def current_option(self) -> str:
        value = self._entry.options.get(self._option_key, FILTER_ALL)
        return t("option_all", self._hass_ref) if value == FILTER_ALL else value

    async def async_select_option(self, option: str) -> None:
        value = FILTER_ALL if option == t("option_all", self._hass_ref) else option
        new_options = {**self._entry.options, self._option_key: value}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)


class StatusSelect(_FilterSelect):
    """Filter by availability status."""

    _attr_icon = "mdi:ev-plug-ccs2"
    _option_key = CONF_STATUS

    def __init__(self, hass: HomeAssistant, coordinator: IchTankeStromCoordinator, entry: ConfigEntry) -> None:
        super().__init__(hass, coordinator, entry)
        self._attr_name = t("status_name", hass)
        self._attr_unique_id = f"{entry.entry_id}_status"
        radius = entry.data.get(CONF_RADIUS_KM)
        self.entity_id = f"select.charging_stations_status_{round(radius)}km_{entry_suffix(entry)}"

    @property
    def options(self) -> list[str]:
        return [
            t("option_all", self._hass_ref),
            t("status_available_only", self._hass_ref),
            t("status_occupied_only", self._hass_ref),
        ]

    @property
    def current_option(self) -> str:
        value = self._entry.options.get(self._option_key, FILTER_ALL)
        if value == STATUS_AVAILABLE:
            return t("status_available_only", self._hass_ref)
        if value == STATUS_OCCUPIED:
            return t("status_occupied_only", self._hass_ref)
        return t("option_all", self._hass_ref)

    async def async_select_option(self, option: str) -> None:
        if option == t("status_available_only", self._hass_ref):
            value = STATUS_AVAILABLE
        elif option == t("status_occupied_only", self._hass_ref):
            value = STATUS_OCCUPIED
        else:
            value = FILTER_ALL
        new_options = {**self._entry.options, self._option_key: value}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)


class OperatorSelect(_FilterSelect):
    """Filter by operator."""

    _attr_icon = "mdi:domain"
    _option_key = CONF_OPERATOR

    def __init__(self, hass: HomeAssistant, coordinator: IchTankeStromCoordinator, entry: ConfigEntry) -> None:
        super().__init__(hass, coordinator, entry)
        self._attr_name = t("operator_name", hass)
        self._attr_unique_id = f"{entry.entry_id}_operator"
        radius = entry.data.get(CONF_RADIUS_KM)
        self.entity_id = f"select.charging_stations_operator_{round(radius)}km_{entry_suffix(entry)}"

    @property
    def options(self) -> list[str]:
        operators = (self.coordinator.data or {}).get("operators", [])
        return [t("option_all", self._hass_ref), *operators]

    @property
    def current_option(self) -> str:
        value = self._entry.options.get(self._option_key, FILTER_ALL)
        return t("option_all", self._hass_ref) if value == FILTER_ALL else value

    async def async_select_option(self, option: str) -> None:
        value = FILTER_ALL if option == t("option_all", self._hass_ref) else option
        new_options = {**self._entry.options, self._option_key: value}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
