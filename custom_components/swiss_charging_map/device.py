"""Shared device info and entity-id helpers for all platforms."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_ENTRY_TYPE,
    CONF_RADIUS_KM,
    DOMAIN,
    ENTRY_TYPE_FAVORITE,
    ENTRY_TYPE_FAVORITE_LOCATION,
)
from .localization import t


def entry_suffix(entry: ConfigEntry) -> str:
    """Short per-entry discriminator for suggested entity ids: the last four
    characters of the config entry id, lower-cased (entry ids are ULIDs, so
    the tail is random and stays fixed for the life of the entry).

    The radius or the favorite's name alone does not tell two entries apart:
    the config flow allows two radius entries at different locations with
    the same radius, and two favorite sites can share a name. Their entities
    would then suggest identical object ids, which Home Assistant resolves
    by appending _2 to whichever entry loads second — an automation copied
    between the entries silently targets the wrong one. The suffix keeps
    them apart. It only affects the id suggested on first creation; unique
    ids are untouched and existing entities keep the ids they have."""
    return entry.entry_id[-4:].lower()


def device_info(hass: HomeAssistant, entry: ConfigEntry) -> DeviceInfo:
    entry_type = entry.data.get(CONF_ENTRY_TYPE)
    if entry_type == ENTRY_TYPE_FAVORITE:
        name = entry.title
        model = "Charging infrastructure data (WFS) — single favorite charge point"
    elif entry_type == ENTRY_TYPE_FAVORITE_LOCATION:
        name = entry.title
        model = "Charging infrastructure data (WFS) — favorite site (all charge points)"
    else:
        name = t("device_name", hass, radius=entry.data.get(CONF_RADIUS_KM))
        model = "Charging infrastructure data (WFS)"
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=name,
        manufacturer="ich-tanke-strom.ch (BFE / EnergieSchweiz / swisstopo)",
        model=model,
        entry_type="service",
    )
