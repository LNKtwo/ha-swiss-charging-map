"""Ad-hoc charging price lookup from the federal geodata portal.

The WFS source this integration reads stations from carries no price
information at all. The public GeoJSON behind map.geo.admin.ch's
charging-station layer does: for operators that publish their ad-hoc
(direct payment) prices to the Swiss eMobility price atlas, the per-site
popup HTML in that file contains a price row (e.g. "0.57 CHF/kWh"),
republished as open data on data.geo.admin.ch. About a quarter of all
Swiss sites carry a price this way; the rest only show a "consult your
provider" fallback and stay unknown here.

This module downloads that file, extracts the price text per site, and
indexes it by EvseID and ChargingStationId so the coordinators can
annotate their stations. Prices change rarely compared to availability,
so one cache shared by every config entry refreshes at most every
PRICE_MAX_AGE_HOURS — and only best-effort: a price fetch failure must
never break a status refresh.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# The GeoJSON rendered by map.geo.admin.ch's "Ladepunkte für Elektroautos"
# layer. Always the German variant — the price value itself ("0.5 CHF/kWh")
# is language-neutral, and the price row is located via the language-
# independent price-atlas link, not the localized label text.
PRICE_DATA_URL = (
    "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/data/"
    "ch.bfe.ladestellen-elektromobilitaet_de.json"
)
PRICE_FETCH_TIMEOUT_SECONDS = 60
PRICE_MAX_AGE_HOURS = 6

_DATA_KEY = f"{DOMAIN}_price_cache"

# The price row only exists for sites with a published price; its label cell
# links to the price-atlas dataset, which uniquely marks the row in every
# language. The value cell is plain text.
_PRICE_ROW = re.compile(
    r"ladepreiskarte[^\"]*\"[^>]*>[^<]*</a>\s*</td>\s*<td>\s*([^<]*?)\s*</td>",
    re.S,
)
# The site's feedback link enumerates every EvseID at the site — the only
# place the (whole-site) GeoJSON exposes them, and exactly the ids the WFS
# source uses, so it doubles as the join key between the two sources.
_STATION_IDS = re.compile(r"stationids=([^\"&]+)")


def _parse_prices(data: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Extract price text per site from the GeoJSON's popup HTML. Returns
    (by_evse_id, by_charging_station_id)."""
    by_evse: dict[str, str] = {}
    by_station: dict[str, str] = {}
    for feature in data.get("features", []):
        description = (feature.get("properties") or {}).get("description") or ""
        price_match = _PRICE_ROW.search(description)
        if not price_match:
            continue
        price = html.unescape(re.sub(r"\s+", " ", price_match.group(1))).strip()
        # Sites without a published price carry the same row with a localized
        # "please consult your provider" fallback text — a real price always
        # contains a digit ("0.5 CHF/kWh"), the fallback never does.
        if not price or not any(ch.isdigit() for ch in price):
            continue
        station_id = feature.get("id")
        if station_id:
            by_station[str(station_id)] = price
        ids_match = _STATION_IDS.search(description)
        if ids_match:
            for evse_id in ids_match.group(1).split(","):
                if evse_id:
                    by_evse[evse_id] = price
    return by_evse, by_station


class PriceCache:
    """One instance per HA instance, shared by every config entry."""

    def __init__(self) -> None:
        self._by_evse: dict[str, str] = {}
        self._by_station: dict[str, str] = {}
        self._fetched_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def async_ensure_fresh(self, hass: HomeAssistant) -> None:
        """Refresh the cache if stale. Best-effort: on failure the previous
        (possibly empty) data stays in place and the next refresh retries."""
        async with self._lock:
            if self._fetched_at and datetime.now() - self._fetched_at < timedelta(hours=PRICE_MAX_AGE_HOURS):
                return
            try:
                session = async_get_clientsession(hass)
                async with session.get(PRICE_DATA_URL, timeout=PRICE_FETCH_TIMEOUT_SECONDS) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
                self._by_evse, self._by_station = await hass.async_add_executor_job(_parse_prices, data)
                self._fetched_at = datetime.now()
                _LOGGER.debug(
                    "Price data refreshed: %d sites with a published price", len(self._by_station)
                )
            except Exception:  # noqa: BLE001 - price lookup is an optional extra, never break a refresh
                # Back off a full cycle after a failure too — without this,
                # an outage of the price source would add a failing extra
                # request to every 5-minute status refresh.
                self._fetched_at = datetime.now()
                _LOGGER.warning("Fetching charging price data failed; prices unavailable", exc_info=True)

    def lookup(self, evse_id: str | None, charging_station_id: str | None) -> str | None:
        """Price text for one connector, or None if its operator publishes
        none. EvseID first — it survives the address-merge grouping where no
        single ChargingStationId covers the site."""
        if evse_id and evse_id in self._by_evse:
            return self._by_evse[evse_id]
        if charging_station_id and charging_station_id in self._by_station:
            return self._by_station[charging_station_id]
        return None


def get_price_cache(hass: HomeAssistant) -> PriceCache:
    if _DATA_KEY not in hass.data:
        hass.data[_DATA_KEY] = PriceCache()
    return hass.data[_DATA_KEY]


def annotate_prices(cache: PriceCache, stations: dict[str, dict]) -> None:
    """Attach a `price` key to every station dict (None when unknown)."""
    for station in stations.values():
        station["price"] = cache.lookup(station.get("evse_id"), station.get("charging_station_id"))
