"""Serving of the bundled Lovelace card.

The card file is served from this integration's frontend/ directory under a
static URL. Registering it as a Lovelace resource is deliberately left to the
user: an integration must not write into the Lovelace storage, which belongs
to the user's dashboard configuration. The README documents the one-time
registration.

The static path is served with cache_headers=False, so a browser picks up an
updated card after a reload without a version query string on the URL.
"""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARD_FILENAME = "swiss-charging-stations-card.js"
CARD_URL_BASE = f"/{DOMAIN}_files/{CARD_FILENAME}"
_SERVED_FLAG = f"{DOMAIN}_card_served"


async def async_serve_card(hass: HomeAssistant) -> None:
    """Serve the bundled card under CARD_URL_BASE.

    Idempotent per HA run; safe to call from every config entry setup."""
    if hass.data.get(_SERVED_FLAG):
        return
    hass.data[_SERVED_FLAG] = True

    card_path = Path(__file__).parent / "frontend" / CARD_FILENAME
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_BASE, str(card_path), cache_headers=False)]
    )
