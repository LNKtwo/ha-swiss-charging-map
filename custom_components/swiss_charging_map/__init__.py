"""ich-tanke-strom.ch Charging Stations – Home Assistant Integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_FAVORITE, ENTRY_TYPE_FAVORITE_LOCATION
from .coordinator import FavoriteLocationCoordinator, FavoriteStationCoordinator, IchTankeStromCoordinator
from .frontend import async_serve_card

_LOGGER = logging.getLogger(__name__)

PLATFORMS_RADIUS = ["sensor", "geo_location", "number", "select"]
PLATFORMS_FAVORITE = ["sensor"]


def _is_radius(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE, "radius") == "radius"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        await async_serve_card(hass)
    except Exception:  # noqa: BLE001 - serving the card must never block integration setup
        _LOGGER.exception("Serving the bundled Lovelace card failed")

    entry_type = entry.data.get(CONF_ENTRY_TYPE)
    if entry_type == ENTRY_TYPE_FAVORITE:
        coordinator = FavoriteStationCoordinator(hass, entry)
    elif entry_type == ENTRY_TYPE_FAVORITE_LOCATION:
        coordinator = FavoriteLocationCoordinator(hass, entry)
    else:
        coordinator = IchTankeStromCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    is_radius = _is_radius(entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_RADIUS if is_radius else PLATFORMS_FAVORITE)

    if not is_radius:
        return True

    # The number/select filter entities write to entry.options — refresh
    # immediately on any change instead of waiting for the next 5-minute poll.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: IchTankeStromCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    platforms = PLATFORMS_RADIUS if _is_radius(entry) else PLATFORMS_FAVORITE
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
