"""Optional Chargeprice price layer (chargeprice.app API).

prices.py covers the ad-hoc price atlas republished by the BFE (about a
quarter of Swiss sites). This module adds structured min/max CHF/kWh from
the Chargeprice API, whose Swiss tariff coverage includes Swisscharge,
MOVE/JOYA, GOFAST, Agrola, Migrol and most other public networks — the
prices a walk-up guest actually pays.

Entirely optional: without an API key in the entry's config the layer
stays dormant and the integration behaves exactly like upstream. Demo API
keys are free for non-commercial use:
https://insights.chargeprice.app/signup?demo=true

Join key: EMI3 EVSE IDs — both ich-tanke-strom.ch and Chargeprice expose
them, so no fuzzy matching is needed. A distance fallback (haversine)
covers sites whose EVSE IDs differ between the sources.

The API returns the cost of a whole session for a given energy/duration;
this module divides by the requested energy to get CHF/kWh. Direct-payment
tariffs (no registration, card at the terminal) are preferred over
subscription tariffs, with the cheapest direct-payment tariff as the
headline "min" price.

Quota care: demo keys are heavily rate-limited, so at most
CHARGEPRICE_MAX_STATIONS_PER_CYCLE stations (nearest first, unpriced or stale
ones only) are priced per batch, at most one batch per area every
CHARGEPRICE_BATCH_INTERVAL_MINUTES. Prices are cached for PRICE_MAX_AGE_HOURS
per search area, and a 429 ends the batch immediately instead of burning
through the remaining quota.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta

from aiohttp import ClientResponseError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CHARGEPRICE_API_URL,
    CHARGEPRICE_BATCH_INTERVAL_MINUTES,
    CHARGEPRICE_MAX_STATIONS_PER_CYCLE,
    CHARGEPRICE_SESSION_ENERGY_KWH,
    CHARGEPRICE_SESSION_MINUTES,
    CHARGEPRICE_SESSION_START_MINUTES,
    CHARGEPRICE_TIMEOUT_SECONDS,
    DEFAULT_CHARGEPRICE_CURRENCY,
    DEFAULT_PRICE_MATCH_RADIUS_M,
    DOMAIN,
    PRICE_MAX_AGE_HOURS,
)

_LOGGER = logging.getLogger(__name__)

_DATA_KEY = f"{DOMAIN}_chargeprice_cache"

# ich-tanke-strom.ch plug labels -> Chargeprice plug enums (enums.md#plugs).
# Matched case-insensitively after stripping separators; unknown labels are
# skipped rather than guessed.
_PLUG_MAP = {
    "ccs": "ccs",
    "ccs2": "ccs",
    "combo": "ccs",
    "combo2": "ccs",
    "type2": "type2",
    "typ2": "type2",
    "type2cable": "type2",
    "type2socket": "type2",
    "chademo": "chademo",
    "type1": "type1",
    "j1772": "type1",
    "schuko": "schuko",
    "cee": "cee",
    "ceed": "cee",
}


def _canonical_plug(label: str) -> str | None:
    key = "".join(ch for ch in str(label).lower() if ch.isalnum())
    return _PLUG_MAP.get(key)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters — good enough for a <500 m fallback."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


class ChargepriceClient:
    """Thin jsonapi client for the two Chargeprice endpoints this uses."""

    def __init__(self, session, api_key: str, currency: str) -> None:
        self._session = session
        self._currency = currency
        self._timeout = ClientTimeout(total=CHARGEPRICE_TIMEOUT_SECONDS)
        self._headers = {"API-Key": api_key, "Content-Type": "application/json", "Accept-Language": "en"}

    async def stations_in_radius(self, lat: float, lon: float, radius_m: float) -> list[dict]:
        """GET /v1/charging_stations — radius search. Returns plain dicts:
        {id, operator_id, latitude, longitude, evse_ids, charge_points}."""
        params = {
            "filter[latitude]": round(lat, 6),
            "filter[longitude]": round(lon, 6),
            "filter[radius]": int(radius_m),
            "filter[country]": "CH",
            "page[size]": 400,
            "page[number]": 1,
        }
        async with self._session.get(
            f"{CHARGEPRICE_API_URL}/charging_stations", params=params, headers=self._headers, timeout=self._timeout
        ) as resp:
            resp.raise_for_status()
            body = await resp.json(content_type=None)
        stations: list[dict] = []
        for item in body.get("data", []):
            attrs = item.get("attributes") or {}
            rel = ((item.get("relationships") or {}).get("operator") or {}).get("data") or {}
            stations.append(
                {
                    "id": item.get("id"),
                    "operator_id": rel.get("id"),
                    "latitude": attrs.get("latitude"),
                    "longitude": attrs.get("longitude"),
                    "evse_ids": attrs.get("evse_ids") or [],
                    "charge_points": attrs.get("charge_points") or [],
                }
            )
        return stations

    async def charge_price(self, lat: float, lon: float, operator_id: str | None, charge_points: list[dict]) -> list[dict]:
        """POST /v1/charge_prices — tariffs for one charge at one station.
        Returns the raw charge_price object list (may be empty)."""
        plugs = []
        for cp in charge_points:
            plug = _canonical_plug(cp.get("plug", ""))
            if plug and cp.get("power"):
                plugs.append({"power": float(cp["power"]), "plug": plug})
        if not plugs:
            return []
        body = {
            "data": {
                "type": "charge_price_request",
                "attributes": {
                    "data_adapter": "chargeprice",
                    "station": {
                        "longitude": round(lon, 6),
                        "latitude": round(lat, 6),
                        "country": "CH",
                        "network": operator_id or "",
                        "charge_points": plugs,
                    },
                    "options": {
                        "energy": CHARGEPRICE_SESSION_ENERGY_KWH,
                        "duration": CHARGEPRICE_SESSION_MINUTES,
                        "start_time": CHARGEPRICE_SESSION_START_MINUTES,
                        "currency": self._currency,
                        "foreign_tariffs": False,
                    },
                },
            }
        }
        async with self._session.post(
            f"{CHARGEPRICE_API_URL}/charge_prices", json=body, headers=self._headers, timeout=self._timeout
        ) as resp:
            resp.raise_for_status()
            body = await resp.json(content_type=None)
        return [d.get("attributes") or {} for d in body.get("data") or []]


class _AreaPrices:
    """Price state for one search area (one radius entry's center + radius)."""

    def __init__(self) -> None:
        self.cp_stations: list[dict] = []
        self.listed_at: datetime | None = None
        # cp station id -> (price summary or None if unpriced, priced_at)
        self.priced: dict[str, tuple[dict | None, datetime]] = {}
        self.by_evse: dict[str, dict] = {}
        self.next_batch_at: datetime | None = None


class ChargepricePriceCache:
    """One instance per HA instance, shared by every config entry — same
    pattern as prices.PriceCache. Prices are kept per search area, since
    every radius entry has its own center: a single shared result set would
    only ever cover the first entry's area."""

    def __init__(self) -> None:
        self._areas: dict[tuple, _AreaPrices] = {}
        self._lock = asyncio.Lock()

    async def async_annotate(
        self,
        hass: HomeAssistant,
        stations: dict[str, dict],
        latitude: float,
        longitude: float,
        radius_km: float,
        api_key: str | None,
        currency: str | None,
        match_radius_m: float | None,
    ) -> None:
        """Best-effort: annotate stations with price_min/price_max/price_provider/
        price_tariff. Never raises; without an API key this is a no-op."""
        if not api_key:
            return
        currency = currency or DEFAULT_CHARGEPRICE_CURRENCY
        match_radius_m = match_radius_m or DEFAULT_PRICE_MATCH_RADIUS_M
        key = (round(latitude, 4), round(longitude, 4), float(radius_km), currency)
        try:
            area = await self.async_ensure_fresh(hass, key, latitude, longitude, radius_km, api_key, currency)
        except Exception:  # noqa: BLE001 - price lookup is an optional extra
            _LOGGER.warning("Chargeprice price lookup failed; prices unavailable", exc_info=True)
            return
        for station in stations.values():
            data = self.lookup(
                area, station.get("evse_id"), station.get("latitude"), station.get("longitude"), match_radius_m
            )
            if data is None:
                continue
            station["price_min"] = data.get("min")
            station["price_max"] = data.get("max")
            station["price_currency"] = data.get("currency")
            station["price_provider"] = data.get("provider")
            station["price_tariff"] = data.get("tariff")

    async def async_ensure_fresh(
        self, hass: HomeAssistant, key: tuple, lat: float, lon: float, radius_km: float, api_key: str, currency: str
    ) -> _AreaPrices:
        async with self._lock:
            area = self._areas.setdefault(key, _AreaPrices())
            now = datetime.now()
            if area.next_batch_at and now < area.next_batch_at:
                return area
            area.next_batch_at = now + timedelta(minutes=CHARGEPRICE_BATCH_INTERVAL_MINUTES)
            try:
                await self._refresh(hass, area, lat, lon, radius_km, api_key, currency)
            except ClientResponseError as err:
                if err.status == 429:
                    # Quota exhausted: skip until the next batch window
                    # instead of burning more requests now.
                    _LOGGER.warning("Chargeprice quota exhausted; retrying in %d min", CHARGEPRICE_BATCH_INTERVAL_MINUTES)
                else:
                    _LOGGER.warning("Fetching Chargeprice data failed; prices unavailable: %s", err)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Fetching Chargeprice data failed; prices unavailable: %s", err)
            return area

    async def _refresh(
        self, hass: HomeAssistant, area: _AreaPrices, lat: float, lon: float, radius_km: float, api_key: str, currency: str
    ) -> None:
        session = async_get_clientsession(hass)
        client = ChargepriceClient(session, api_key, currency)
        now = datetime.now()
        max_age = timedelta(hours=PRICE_MAX_AGE_HOURS)

        if area.listed_at is None or now - area.listed_at >= max_age:
            area.cp_stations = await client.stations_in_radius(lat, lon, radius_km * 1000)
            area.listed_at = now
            known_ids = {cp["id"] for cp in area.cp_stations}
            area.priced = {k: v for k, v in area.priced.items() if k in known_ids}

        # Price the nearest stations that are unpriced or stale, at most
        # CHARGEPRICE_MAX_STATIONS_PER_CYCLE per batch — later batches pick
        # up where this one stopped, so coverage grows over time.
        candidates = [
            cp
            for cp in area.cp_stations
            if cp["operator_id"]
            and cp["latitude"] is not None
            and cp["longitude"] is not None
            and (cp["id"] not in area.priced or now - area.priced[cp["id"]][1] >= max_age)
        ]
        candidates.sort(key=lambda cp: _haversine_m(lat, lon, cp["latitude"], cp["longitude"]))
        try:
            for cp in candidates[:CHARGEPRICE_MAX_STATIONS_PER_CYCLE]:
                prices = await client.charge_price(cp["latitude"], cp["longitude"], cp["operator_id"], cp["charge_points"])
                area.priced[cp["id"]] = (_summarize_prices(prices, CHARGEPRICE_SESSION_ENERGY_KWH), now)
        finally:
            # Keep whatever got priced before an error (e.g. a 429 mid-batch).
            area.by_evse = {}
            for cp in area.cp_stations:
                summary = area.priced.get(cp["id"], (None, now))[0]
                if summary is None:
                    continue
                for evse_id in cp["evse_ids"]:
                    area.by_evse[str(evse_id).strip().upper()] = summary
        _LOGGER.debug(
            "Chargeprice refreshed: %d of %d stations in radius priced",
            sum(1 for summary, _ in area.priced.values() if summary is not None),
            len(area.cp_stations),
        )

    @staticmethod
    def lookup(
        area: _AreaPrices,
        evse_id: str | None,
        latitude: float | None,
        longitude: float | None,
        match_radius_m: float,
    ) -> dict | None:
        """Price summary for one connector. EVSE-ID join first; then the
        nearest priced Chargeprice station within match_radius_m."""
        if evse_id:
            data = area.by_evse.get(str(evse_id).strip().upper())
            if data is not None:
                return data
        if latitude is None or longitude is None:
            return None
        best, best_d = None, match_radius_m
        for cp in area.cp_stations:
            summary = area.priced.get(cp["id"], (None, None))[0]
            if summary is None or cp["latitude"] is None or cp["longitude"] is None:
                continue
            d = _haversine_m(latitude, longitude, cp["latitude"], cp["longitude"])
            if d < best_d:
                best, best_d = summary, d
        return best


def _summarize_prices(charge_prices: list[dict], energy_kwh: float) -> dict | None:
    """Reduce the tariff list to min/max CHF/kWh. Direct-payment tariffs (the
    walk-up price — what an app/terminal payment costs, no subscription) are
    preferred; subscription tariffs only fill in when no direct-payment
    tariff publishes a price. Returns None when nothing priced."""
    def _kwh_prices(rows: list[dict]) -> list[float]:
        out = []
        for tariff in rows:
            for cp_price in tariff.get("charge_point_prices") or []:
                price = cp_price.get("price")
                if price is None or not energy_kwh:
                    continue
                out.append(float(price) / energy_kwh)
        return out

    direct = [t for t in charge_prices if t.get("direct_payment")]
    pool = direct or charge_prices
    kwh = _kwh_prices(pool)
    if not kwh:
        return None
    def _tariff_min(tariff: dict) -> float:
        prices = [
            float(cp["price"]) / energy_kwh
            for cp in tariff.get("charge_point_prices") or []
            if cp.get("price") is not None
        ]
        return min(prices, default=math.inf)

    best = min(pool, key=lambda t: (_tariff_min(t), not t.get("direct_payment")))
    return {
        "min": round(min(kwh), 3),
        "max": round(max(kwh), 3),
        "currency": (charge_prices[0] or {}).get("currency", "CHF"),
        "provider": best.get("provider") or "",
        "tariff": best.get("tariff_name") or "",
        "direct_payment": bool(best.get("direct_payment")),
    }


def get_chargeprice_cache(hass: HomeAssistant) -> ChargepricePriceCache:
    if _DATA_KEY not in hass.data:
        hass.data[_DATA_KEY] = ChargepricePriceCache()
    return hass.data[_DATA_KEY]
