"""DataUpdateCoordinator for charging stations from ich-tanke-strom.ch (BFE/EnergieSchweiz).

Uses the official WFS/GeoServer REST API, no authentication required. Bbox
query (rough server-side pre-filtering) plus exact Haversine distance
filtering in code — a tested DWITHIN radius query did not return correctly
filtered results on this server.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MIN_POWER_KW,
    CONF_OPERATOR,
    CONF_PLUG_TYPE,
    CONF_RADIUS_KM,
    CONF_STATION_ID,
    CONF_STATION_LOCATION_EVSE_IDS,
    CONF_STATION_LOCATION_ID,
    CONF_STATUS,
    DEFAULT_MIN_POWER_KW,
    DOMAIN,
    FETCH_TIMEOUT_SECONDS,
    FILTER_ALL,
    KM_PER_DEGREE,
    KNOWN_PLUG_TYPES,
    STATUS_AVAILABLE,
    STATUS_OCCUPIED,
    UPDATE_INTERVAL_MINUTES,
    WFS_URL,
)
from .chargeprice import get_chargeprice_cache
from .const import (
    CONF_CHARGEPRICE_API_KEY,
    CONF_CHARGEPRICE_CURRENCY,
    CONF_PRICE_MATCH_RADIUS_M,
    DEFAULT_CHARGEPRICE_CURRENCY,
    DEFAULT_PRICE_MATCH_RADIUS_M,
)
from .prices import annotate_prices, get_price_cache

_LOGGER = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _keeps_existing(existing: dict | None, new: dict) -> bool:
    """Whether to keep an already collected record over a new one with the
    same EvseID. Some charge points are published twice by different feeds
    (observed 2026-10-28 at Mall of Switzerland: once by MOVE with live
    status, once via Energie 360° with "Unknown") — the live one must win."""
    if existing is None:
        return False
    return existing["status"] != "Unknown" or new["status"] == "Unknown"


def _parse_station(feature: dict, lat: float | None = None, lon: float | None = None) -> dict | None:
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    station_lon, station_lat = coords[0], coords[1]

    # The source serializes single-element complex fields inconsistently —
    # a handful of stations return these as a bare dict instead of a list
    # (observed live for ChargingStationNames, 2 of ~6,000 stations), which
    # used to crash the whole radius refresh. Normalize everything.
    facilities = [f for f in _as_list(props.get("ChargingFacilities")) if isinstance(f, dict)]
    power_kw = max(((f.get("Power") or 0) for f in facilities), default=0)

    plugs = list(_as_list(props.get("Plugs")))
    names = [n for n in _as_list(props.get("ChargingStationNames")) if isinstance(n, dict)]

    address = props.get("Address", {}) or {}
    evse_id = props.get("EvseID")
    station_id = feature.get("id") or evse_id
    distance_km = (
        round(haversine_km(lat, lon, station_lat, station_lon), 2) if lat is not None and lon is not None else None
    )

    return {
        "id": station_id,
        "evse_id": evse_id,
        "charging_station_id": props.get("ChargingStationId"),
        "latitude": station_lat,
        "longitude": station_lon,
        "distance_km": distance_km,
        "status": props.get("EvseStatus") or "Unknown",
        "power_kw": power_kw,
        "plugs": plugs,
        "operator": props.get("OperatorID"),
        "station_name": names[0].get("value") if names else None,
        "street": address.get("Street"),
        "city": address.get("City"),
        "postal_code": address.get("PostalCode"),
        "last_update": props.get("lastUpdate"),
        "open_24h": props.get("IsOpen24Hours"),
        "opening_times": [o for o in _as_list(props.get("OpeningTimes")) if isinstance(o, dict)],
        "payment_options": props.get("PaymentOptions") or [],
        "renewable_energy": props.get("RenewableEnergy"),
        "accessibility": props.get("Accessibility"),
    }


async def async_fetch_stations(hass: HomeAssistant, lat: float, lon: float, radius_km: float) -> dict[str, dict]:
    session = async_get_clientsession(hass)

    lat_delta = radius_km / KM_PER_DEGREE
    lon_delta = radius_km / (KM_PER_DEGREE * max(0.1, math.cos(math.radians(lat))))
    bbox = f"{lon - lon_delta},{lat - lat_delta},{lon + lon_delta},{lat + lat_delta}"

    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": "ich-tanke-strom:evse",
        "outputFormat": "application/json",
        # Only the properties _parse_station actually reads — roughly halves
        # response size and server time on large radii. Feature ids (used as
        # stable entity unique_ids) are unaffected, verified against the
        # unslimmed response.
        "propertyName": (
            "EvseID,ChargingStationId,EvseStatus,ChargingFacilities,Plugs,"
            "Address,ChargingStationNames,OperatorID,lastUpdate,IsOpen24Hours,"
            "OpeningTimes,PaymentOptions,RenewableEnergy,Accessibility,geometry"
        ),
        "cql_filter": f"bbox(geometry,{bbox})",
    }
    async with session.get(WFS_URL, params=params, timeout=FETCH_TIMEOUT_SECONDS) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)

    stations: dict[str, dict] = {}
    key_by_evse: dict[str, str] = {}
    for feature in data.get("features", []):
        try:
            station = _parse_station(feature, lat, lon)
        except Exception:  # noqa: BLE001 - one malformed feature must never kill the whole refresh
            _LOGGER.debug("Skipping malformed station feature %s", feature.get("id"), exc_info=True)
            continue
        if station is None:
            continue
        if station["distance_km"] > radius_km:
            continue
        # Duplicates share the EvseID and often the feature id too.
        evse_id = station.get("evse_id")
        if evse_id in key_by_evse:
            if _keeps_existing(stations[key_by_evse[evse_id]], station):
                continue
            del stations[key_by_evse[evse_id]]
        stations[station["id"]] = station
        if evse_id:
            key_by_evse[evse_id] = station["id"]
    return stations


async def async_fetch_station_by_id(hass: HomeAssistant, evse_id: str) -> dict | None:
    """Fetch a single station's current data by its EvseID — the stable,
    human/QR-code-facing identifier printed on the charger itself and shown
    on ich-tanke-strom.ch, as opposed to the opaque WFS feature id used to
    key the radius view's stations dict. Independent of any location/radius,
    used both to validate a favorite during setup and to refresh it
    afterwards. Returns None if no station matches."""
    session = async_get_clientsession(hass)
    escaped_id = evse_id.replace("'", "''")  # CQL string-literal escaping
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": "ich-tanke-strom:evse",
        "outputFormat": "application/json",
        "cql_filter": f"EvseID='{escaped_id}'",
    }
    async with session.get(WFS_URL, params=params, timeout=30) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    best = None
    for feature in data.get("features", []):
        station = _parse_station(feature)
        if station is not None and not _keeps_existing(best, station):
            best = station
    return best


async def async_fetch_stations_by_evse_ids(hass: HomeAssistant, evse_ids: list[str]) -> dict[str, dict]:
    """Fetch specific connectors by their EvseIDs. Used to refresh a location
    favorite whose group was formed via the address fallback in
    group_by_location, where no single ChargingStationId covers the whole
    site. Returns a dict keyed by evse_id, empty if none of them exist
    anymore."""
    session = async_get_clientsession(hass)
    escaped = ",".join(f"'{e.replace(chr(39), chr(39) * 2)}'" for e in evse_ids)
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": "ich-tanke-strom:evse",
        "outputFormat": "application/json",
        "cql_filter": f"EvseID IN ({escaped})",
    }
    async with session.get(WFS_URL, params=params, timeout=30) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    stations: dict[str, dict] = {}
    for feature in data.get("features", []):
        station = _parse_station(feature)
        if station is None or not station.get("evse_id"):
            continue
        if _keeps_existing(stations.get(station["evse_id"]), station):
            continue
        stations[station["evse_id"]] = station
    return stations


async def async_fetch_station_location(hass: HomeAssistant, charging_station_id: str) -> dict[str, dict]:
    """Fetch every charge point (EVSE) sharing the given ChargingStationId —
    i.e. every connector at one physical site. Returns a dict keyed by
    evse_id, empty if the location no longer has any connectors."""
    session = async_get_clientsession(hass)
    escaped_id = charging_station_id.replace("'", "''")  # CQL string-literal escaping
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": "ich-tanke-strom:evse",
        "outputFormat": "application/json",
        "cql_filter": f"ChargingStationId='{escaped_id}'",
    }
    async with session.get(WFS_URL, params=params, timeout=30) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    stations: dict[str, dict] = {}
    for feature in data.get("features", []):
        station = _parse_station(feature)
        if station is None or not station.get("evse_id"):
            continue
        if _keeps_existing(stations.get(station["evse_id"]), station):
            continue
        stations[station["evse_id"]] = station
    return stations


SITE_RESOLVE_RADIUS_KM = 0.3


async def async_resolve_site(hass: HomeAssistant, station: dict) -> dict | None:
    """Expand one resolved connector to its full physical site.

    A direct EvseID or ChargingStationId lookup can under-count a site:
    several operators give each pole (Migros: CH*MIG*P*1797 vs *1813) or even
    each connector (aggregators, where ChargingStationId == EvseID) its own
    id, so only the operator+address merge in group_by_location sees the
    whole site. Fetch everything within a small radius around the connector's
    coordinates, group it, and return the merged group containing the
    connector — or None if it can't be resolved (caller falls back to the
    ungrouped result).
    """
    lat, lon = station.get("latitude"), station.get("longitude")
    evse_id = station.get("evse_id")
    if lat is None or lon is None or not evse_id:
        return None
    nearby = await async_fetch_stations(hass, lat, lon, SITE_RESOLVE_RADIUS_KM)
    for group in group_by_location(nearby).values():
        if evse_id in group["connectors"]:
            return group
    return None


def _address_key(street: str | None, postal_code: str | None, city: str | None) -> str | None:
    parts = [(street or "").strip().lower(), (postal_code or "").strip().lower(), (city or "").strip().lower()]
    if not any(parts):
        return None
    return "|".join(parts)


def group_by_location(stations: dict[str, dict]) -> dict[str, dict]:
    """Group EVSE-level station dicts by their physical site — many real
    charging sites have several connectors that all sit at identical GPS
    coordinates, so treating each one as its own map marker/entity produces
    stacked, indistinguishable results.

    Primary key is the API's ChargingStationId. That alone isn't enough
    though — verified against live data on 2026-07-17, two distinct cases
    still split one physical site into several groups: (1) several smaller
    operators (Tesla, various e-mobility CH aggregator IDs, MOVE/CCC) report
    no shared site ID at all, each connector echoing its own EvseID back as
    its ChargingStationId; (2) some operators (e.g. Migros/Migrol — reported
    by a user: "Migros | Möhlin 1" / "Migros | Möhlin 2") give each pole at
    one site its own real, distinct ChargingStationId. Both cases are caught
    by a second pass: any of the primary groups that share the same
    operator + street + postal_code + city get merged together. Groups whose
    key is unique already (the common case — GOFAST, Shell evpass, Migrol,
    Lidl, Energie 360°, ... — one real shared ChargingStationId, nothing else
    at that address+operator) pass through untouched, keeping their real
    ChargingStationId as location_id.

    Returns one summary dict per location: connector list plus aggregated
    count/availability, keyed by charging_station_id — or, for a merged
    group, a synthetic `addr_<hash>` id (flagged `is_synthetic: True`, since
    no single ChargingStationId covers the merged group anymore; see
    async_fetch_stations_by_evse_ids)."""
    groups: dict[str, dict] = {}
    for evse_id, s in stations.items():
        location_id = s.get("charging_station_id") or evse_id
        groups.setdefault(location_id, {"location_id": location_id, "connectors": {}})["connectors"][evse_id] = s

    merged: dict[str, dict] = {}
    by_key: dict[tuple[str, str], list[dict]] = {}
    for location_id, g in groups.items():
        first = next(iter(g["connectors"].values()))
        addr_key = _address_key(first.get("street"), first.get("postal_code"), first.get("city"))
        if addr_key is None:
            merged[location_id] = g
            continue
        key = (addr_key, (first.get("operator") or "").strip().lower())
        by_key.setdefault(key, []).append(g)

    for key, group_list in by_key.items():
        if len(group_list) == 1:
            g = group_list[0]
            merged[g["location_id"]] = g
            continue
        synthetic_id = f"addr_{hashlib.md5('|'.join(key).encode()).hexdigest()[:12]}"
        combined_connectors: dict[str, dict] = {}
        for g in group_list:
            combined_connectors.update(g["connectors"])
        merged[synthetic_id] = {"location_id": synthetic_id, "connectors": combined_connectors, "is_synthetic": True}

    for location_id, g in merged.items():
        connectors = g["connectors"]
        first = next(iter(connectors.values()))
        g["station_name"] = first.get("station_name")
        g["street"] = first.get("street")
        g["city"] = first.get("city")
        g["postal_code"] = first.get("postal_code")
        g["operator"] = first.get("operator")
        g["latitude"] = first.get("latitude")
        g["longitude"] = first.get("longitude")
        g["distance_km"] = first.get("distance_km")
        g["open_24h"] = first.get("open_24h")
        g["opening_times"] = first.get("opening_times") or []
        g["count_total"] = len(connectors)
        g["count_available"] = sum(1 for c in connectors.values() if c.get("status") == "Available")
        # Published ad-hoc price, when the coordinator annotated one (see
        # prices.py). Site-level by nature — every connector at a site
        # carries the same published price.
        g["price"] = next((c.get("price") for c in connectors.values() if c.get("price")), None)
        kwh = [c["price_kwh"] for c in connectors.values() if c.get("price_kwh") is not None]
        g["price_kwh"] = min(kwh) if kwh else None
        # Structured prices from the optional Chargeprice layer: aggregate
        # the site's connector prices (usually all identical per site).
        mins = [c["price_min"] for c in connectors.values() if c.get("price_min") is not None]
        maxs = [c["price_max"] for c in connectors.values() if c.get("price_max") is not None]
        g["price_min"] = min(mins) if mins else None
        g["price_max"] = max(maxs) if maxs else None
        g["price_currency"] = next((c.get("price_currency") for c in connectors.values() if c.get("price_currency")), None)
        g["price_provider"] = next((c.get("price_provider") for c in connectors.values() if c.get("price_provider")), None)
        g.setdefault("is_synthetic", False)
    return merged


def _parse_hhmm(value) -> int | None:
    """'HH:MM' -> minutes since midnight, None if unparseable."""
    try:
        hours, minutes = str(value).split(":")
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return None


def is_open_now(opening_times: list | None, now: datetime | None = None) -> bool | None:
    """Evaluate the source's structured OpeningTimes schedule.

    Format (observed live, e.g. Migros):
    [{"on": "Saturday", "Period": [{"begin": "07:30", "end": "20:00"}]}, ...]

    Stations are all in Switzerland, so the schedule is evaluated in
    Europe/Zurich regardless of the HA instance's timezone. Returns None
    when no schedule data is present (24h sites leave OpeningTimes empty) —
    callers must treat that as "unknown", not "closed". A weekday absent
    from a non-empty schedule counts as closed on that day.
    """
    if not opening_times:
        return None
    try:
        now = now or datetime.now(ZoneInfo("Europe/Zurich"))
        weekday = now.strftime("%A")
        minutes = now.hour * 60 + now.minute
        for entry in opening_times:
            if not isinstance(entry, dict) or entry.get("on") != weekday:
                continue
            for period in _as_list(entry.get("Period")):
                if not isinstance(period, dict):
                    continue
                begin = _parse_hhmm(period.get("begin"))
                end = _parse_hhmm(period.get("end"))
                if begin is None or end is None:
                    continue
                if begin <= end:
                    if begin <= minutes < end:
                        return True
                # Overnight period (e.g. 22:00-06:00) wraps past midnight
                elif minutes >= begin or minutes < end:
                    return True
        return False
    except Exception:  # noqa: BLE001 - malformed schedule data must never break a refresh
        return None


API_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def weekly_opening_periods(opening_times: list | None) -> dict[int, list[str]] | None:
    """The source's OpeningTimes schedule as weekday index (0 = Monday) ->
    sorted display periods ('07:30–20:00'). Days the schedule omits are
    absent (closed all day). Returns None when there is no usable schedule
    data at all (e.g. 24h sites leave OpeningTimes empty)."""
    if not opening_times:
        return None
    try:
        week: dict[int, list[str]] = {}
        for entry in opening_times:
            if not isinstance(entry, dict) or entry.get("on") not in API_WEEKDAYS:
                continue
            index = API_WEEKDAYS.index(entry["on"])
            for period in _as_list(entry.get("Period")):
                if isinstance(period, dict) and period.get("begin") and period.get("end"):
                    week.setdefault(index, []).append(f"{period['begin']}–{period['end']}")
        for periods in week.values():
            periods.sort()
        return week or None
    except Exception:  # noqa: BLE001 - malformed schedule data must never break a refresh
        return None


def is_closed_all_day_today(location: dict, now: datetime | None = None) -> bool:
    """True when the schedule marks today as fully closed (no opening
    periods at all, e.g. Sundays at supermarket sites) — lets UIs say
    "closed today" instead of just "closed" (which also covers being
    outside today's hours)."""
    if location.get("open_24h"):
        return False
    week = weekly_opening_periods(location.get("opening_times"))
    if not week:
        return False
    now = now or datetime.now(ZoneInfo("Europe/Zurich"))
    return not week.get(now.weekday())


def site_status(location: dict) -> str:
    """Derived overall status of a whole site. Returns one of:
    available / occupied / closed / out_of_service / unknown.

    Closed is detected two ways: (1) the structured OpeningTimes schedule
    says the site is currently outside its opening hours — this wins even
    over Available connectors, since some operators keep reporting Available
    while the site is inaccessible (user report, 2026-07-19); (2) no
    schedule data, but every connector is OutOfService at a non-24h site —
    that pattern reliably means "closed right now" as opposed to a genuinely
    broken 24h site."""
    connectors = location.get("connectors", {})
    statuses = {c.get("status") for c in connectors.values()}
    if not location.get("open_24h") and is_open_now(location.get("opening_times")) is False:
        return "closed"
    if "Available" in statuses:
        return "available"
    if "Occupied" in statuses:
        return "occupied"
    if statuses and statuses <= {"OutOfService"}:
        return "out_of_service" if location.get("open_24h") else "closed"
    return "unknown"


def icon_for_status(status: str | None) -> str:
    if status == "Available":
        return "mdi:ev-station"
    if status == "Occupied":
        return "mdi:car-electric"
    if status == "OutOfService":
        return "mdi:alert-circle-outline"
    return "mdi:help-circle-outline"


def apply_filters(
    stations: dict[str, dict],
    min_power_kw: float,
    plug_type: str,
    status: str,
    operator: str,
) -> dict[str, dict]:
    """Filter stations using canonical (language-independent) filter values."""
    result = {}
    for station_id, s in stations.items():
        if s["power_kw"] < min_power_kw:
            continue
        if plug_type != FILTER_ALL and plug_type not in s["plugs"]:
            continue
        if status == STATUS_AVAILABLE and s["status"] != "Available":
            continue
        if status == STATUS_OCCUPIED and s["status"] != "Occupied":
            continue
        if operator != FILTER_ALL and s["operator"] != operator:
            continue
        result[station_id] = s
    return result


class IchTankeStromCoordinator(DataUpdateCoordinator[dict]):
    """Fetches charging stations within the configured radius and applies the
    current (live-adjustable) filters from the config entry's options."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._entry = entry

    async def _async_update_data(self) -> dict:
        data = self._entry.data
        try:
            all_stations = await async_fetch_stations(
                self.hass,
                data[CONF_LATITUDE],
                data[CONF_LONGITUDE],
                data[CONF_RADIUS_KM],
            )
        except Exception as err:
            raise UpdateFailed(f"ich-tanke-strom.ch unreachable: {err}") from err

        price_cache = get_price_cache(self.hass)
        await price_cache.async_ensure_fresh(self.hass)
        annotate_prices(price_cache, all_stations)

        # Optional Chargeprice layer (needs an API key; a silent no-op
        # otherwise). Best-effort — a price failure must never break a
        # status refresh.
        entry_opts = self._entry.options
        cp_cache = get_chargeprice_cache(self.hass)
        await cp_cache.async_annotate(
            self.hass,
            all_stations,
            data[CONF_LATITUDE],
            data[CONF_LONGITUDE],
            data[CONF_RADIUS_KM],
            entry_opts.get(CONF_CHARGEPRICE_API_KEY, self._entry.data.get(CONF_CHARGEPRICE_API_KEY)),
            entry_opts.get(CONF_CHARGEPRICE_CURRENCY, self._entry.data.get(CONF_CHARGEPRICE_CURRENCY, DEFAULT_CHARGEPRICE_CURRENCY)),
            entry_opts.get(CONF_PRICE_MATCH_RADIUS_M, self._entry.data.get(CONF_PRICE_MATCH_RADIUS_M, DEFAULT_PRICE_MATCH_RADIUS_M)),
        )

        options = self._entry.options
        filtered = apply_filters(
            all_stations,
            options.get(CONF_MIN_POWER_KW, DEFAULT_MIN_POWER_KW),
            options.get(CONF_PLUG_TYPE, FILTER_ALL),
            options.get(CONF_STATUS, FILTER_ALL),
            options.get(CONF_OPERATOR, FILTER_ALL),
        )

        plug_types = sorted({p for s in all_stations.values() for p in s["plugs"]})
        operators = sorted({s["operator"] for s in all_stations.values() if s["operator"]})

        # Available count per plug type. Respects the min-power and operator
        # filters but deliberately ignores the plug-type and status filters —
        # those only shape the map view, and a "free CCS" sensor must not
        # drop to 0 just because the map is currently filtered to Type 2.
        # A station listing several plug types counts once per type.
        base = apply_filters(
            all_stations,
            options.get(CONF_MIN_POWER_KW, DEFAULT_MIN_POWER_KW),
            FILTER_ALL,
            FILTER_ALL,
            options.get(CONF_OPERATOR, FILTER_ALL),
        )
        available_by_plug_type = {p: 0 for p in KNOWN_PLUG_TYPES}
        for s in base.values():
            if s["status"] != "Available":
                continue
            for p in s["plugs"]:
                available_by_plug_type[p] = available_by_plug_type.get(p, 0) + 1

        return {
            "all_stations": all_stations,
            "filtered_stations": filtered,
            # One entry per physical site (connectors that pass the filters,
            # grouped) — the map shows these instead of per-connector markers.
            "filtered_locations": group_by_location(filtered),
            "plug_types": plug_types,
            "operators": operators,
            "available_by_plug_type": available_by_plug_type,
            "count_total": len(all_stations),
            "count_filtered": len(filtered),
            "count_available_filtered": sum(
                1 for s in filtered.values() if s["status"] == "Available"
            ),
        }


class FavoriteStationCoordinator(DataUpdateCoordinator[dict]):
    """Fetches a single pinned favorite station's current status by its
    EvseID — independent of any location or radius."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._entry = entry

    async def _async_update_data(self) -> dict:
        evse_id = self._entry.data[CONF_STATION_ID]
        try:
            station = await async_fetch_station_by_id(self.hass, evse_id)
        except Exception as err:
            raise UpdateFailed(f"ich-tanke-strom.ch unreachable: {err}") from err
        if station is None:
            raise UpdateFailed(f"Station {evse_id} no longer found in ich-tanke-strom.ch data")
        price_cache = get_price_cache(self.hass)
        await price_cache.async_ensure_fresh(self.hass)
        station["price"] = price_cache.lookup(station.get("evse_id"), station.get("charging_station_id"))
        return station


class FavoriteLocationCoordinator(DataUpdateCoordinator[dict]):
    """Fetches every charge point at a single pinned physical site by its
    ChargingStationId — independent of any search location or radius."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._entry = entry

    async def _async_update_data(self) -> dict:
        location_id = self._entry.data[CONF_STATION_LOCATION_ID]
        evse_ids = self._entry.data.get(CONF_STATION_LOCATION_EVSE_IDS)
        try:
            if evse_ids:
                # Synthetic (address-merged) location — no single ChargingStationId
                # covers the whole site, so refetch by the pinned EvseIDs instead.
                connectors = await async_fetch_stations_by_evse_ids(self.hass, evse_ids)
            else:
                connectors = await async_fetch_station_location(self.hass, location_id)
        except Exception as err:
            raise UpdateFailed(f"ich-tanke-strom.ch unreachable: {err}") from err
        if not connectors:
            raise UpdateFailed(f"Location {location_id} no longer has any connectors in ich-tanke-strom.ch data")

        price_cache = get_price_cache(self.hass)
        await price_cache.async_ensure_fresh(self.hass)
        annotate_prices(price_cache, connectors)

        groups = group_by_location(connectors)
        if evse_ids:
            return max(groups.values(), key=lambda g: len(g["connectors"]))
        return groups[location_id]
