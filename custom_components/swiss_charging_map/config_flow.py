"""Config flow for the ich-tanke-strom.ch charging stations integration.

Two independent kinds of entry, chosen in the first step:
- Radius overview (original behavior): many stations within a live-filterable
  area around a location.
- Favorite: pins exactly one specific station, independent of any location
  or radius. Repeatable — add the integration again for another favorite.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_ENTRY_TYPE,
    CONF_FAVORITE_NAME,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MIN_POWER_KW,
    CONF_PLUG_TYPE,
    CONF_PLUG_TYPE_SENSORS,
    CONF_RADIUS_KM,
    CONF_STATION_ID,
    CONF_STATION_LOCATION_EVSE_IDS,
    CONF_STATION_LOCATION_ID,
    DEFAULT_MIN_POWER_KW,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    MAX_RADIUS_KM,
    ENTRY_TYPE_FAVORITE,
    ENTRY_TYPE_FAVORITE_LOCATION,
    ENTRY_TYPE_RADIUS,
    FILTER_ALL,
    KNOWN_PLUG_TYPES,
)
from .coordinator import (
    apply_filters,
    async_fetch_station_by_id,
    async_fetch_station_location,
    async_fetch_stations,
    async_resolve_site,
    group_by_location,
)
from .localization import location_display_label, station_display_label, t
from .const import (
    CONF_CHARGEPRICE_API_KEY,
    CONF_CHARGEPRICE_CURRENCY,
    CONF_PRICE_MATCH_RADIUS_M,
    DEFAULT_CHARGEPRICE_CURRENCY,
    DEFAULT_PRICE_MATCH_RADIUS_M,
)
from .prices import annotate_prices, get_price_cache

CONF_MODE = "mode"
MODE_RADIUS = "radius"
MODE_FAVORITE = "favorite"

CONF_FAVORITE_SCOPE = "favorite_scope"
SCOPE_SINGLE = "single"
SCOPE_SITE = "site"

_LOCATION_PREFIX = "LOCATION:"  # sentinel prefix for a whole-location pick — never collides with a real EvseID

# Radius input with the upper bound visible/enforced in the UI. Bigger radii
# strain both the source server (20-40+ s per fetch) and Home Assistant
# (thousands of stations); see MAX_RADIUS_KM in const.py.
_RADIUS_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=MAX_RADIUS_KM, step=0.5, unit_of_measurement="km", mode=NumberSelectorMode.BOX)
)


class IchTankeStromConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup wizard: pick radius overview or favorite mode, then configure it."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IchTankeStromOptionsFlow()

    def __init__(self) -> None:
        self._favorite_candidates: dict[str, dict] = {}
        # Carried between favorite -> favorite_scope when an entered EvseID
        # turns out to sit at a multi-connector site.
        self._pending_station: dict | None = None
        self._pending_site: dict | None = None
        self._pending_name: str | None = None
        # Carried between favorite -> favorite_confirm (ID path): exactly one
        # of these is set — a single resolved connector, or a site id whose
        # connectors sit in _favorite_candidates.
        self._confirm_station: dict | None = None
        self._confirm_location_id: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            if user_input[CONF_MODE] == MODE_FAVORITE:
                return await self.async_step_favorite()
            return await self.async_step_radius()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=MODE_RADIUS): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=MODE_RADIUS, label=t("mode_radius", self.hass)),
                            SelectOptionDict(value=MODE_FAVORITE, label=t("mode_favorite", self.hass)),
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_radius(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Original behavior: a live-filterable overview of every station
        within a location + radius."""
        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS_KM]
            await self.async_set_unique_id(f"radius_{round(lat, 2)}_{round(lon, 2)}_{radius}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=t("device_name", self.hass, radius=radius),
                data={
                    CONF_ENTRY_TYPE: ENTRY_TYPE_RADIUS,
                    CONF_LATITUDE: lat,
                    CONF_LONGITUDE: lon,
                    CONF_RADIUS_KM: radius,
                    CONF_CHARGEPRICE_API_KEY: user_input.get(CONF_CHARGEPRICE_API_KEY, ""),
                    CONF_CHARGEPRICE_CURRENCY: user_input.get(CONF_CHARGEPRICE_CURRENCY, DEFAULT_CHARGEPRICE_CURRENCY),
                    CONF_PRICE_MATCH_RADIUS_M: user_input.get(CONF_PRICE_MATCH_RADIUS_M, DEFAULT_PRICE_MATCH_RADIUS_M),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): vol.Coerce(float),
                vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): _RADIUS_SELECTOR,
                # Optional Chargeprice price layer — empty keeps the entry on
                # the BFE ad-hoc atlas only (upstream behaviour). Free demo
                # keys: insights.chargeprice.app/signup?demo=true
                vol.Optional(CONF_CHARGEPRICE_API_KEY, default=""): str,
                vol.Optional(CONF_CHARGEPRICE_CURRENCY, default=DEFAULT_CHARGEPRICE_CURRENCY): str,
                vol.Optional(CONF_PRICE_MATCH_RADIUS_M, default=DEFAULT_PRICE_MATCH_RADIUS_M): vol.All(
                    vol.Coerce(int), vol.Range(min=50, max=500)
                ),
            }
        )
        return self.async_show_form(step_id="radius", data_schema=schema)

    async def async_step_favorite(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Pin one station as a favorite — either by its EvseID directly
        (e.g. from a QR code on the charger), or by searching near a
        location and picking one from a list on the next screen."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = (user_input.get(CONF_STATION_ID) or "").strip()
            if station_id:
                try:
                    station = await async_fetch_station_by_id(self.hass, station_id)
                    # Not an EvseID? Maybe it's a whole site's
                    # ChargingStationId — then favorite the whole site.
                    location_connectors = (
                        None if station is not None else await async_fetch_station_location(self.hass, station_id)
                    )
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    if station is not None:
                        # The EvseID names one connector, but the physical
                        # site may hold more — several operators give each
                        # pole or even each connector its own id, so only
                        # the operator+address merge sees the whole site
                        # (user report 2026-07-19: 1 of 3 / 1 of 8 shown).
                        # Resolve the site and let the user pick the scope.
                        try:
                            site = await async_resolve_site(self.hass, station)
                        except Exception:
                            site = None  # best-effort — fall back to the single connector
                        if site and site["count_total"] > 1:
                            self._pending_station = station
                            self._pending_site = site
                            self._pending_name = user_input.get(CONF_FAVORITE_NAME)
                            return await self.async_step_favorite_scope()
                        # Single-connector site: confirm + optional custom name.
                        self._confirm_station = station
                        self._confirm_location_id = None
                        return await self.async_step_favorite_confirm()
                    if location_connectors:
                        # A ChargingStationId lookup can also under-count the
                        # site (Migros: one real id per pole at the same
                        # address) — expand through the merge when it finds
                        # more connectors than the direct lookup did.
                        connectors = location_connectors
                        location_id = station_id
                        try:
                            site = await async_resolve_site(self.hass, next(iter(location_connectors.values())))
                        except Exception:
                            site = None
                        if site and len(site["connectors"]) > len(location_connectors):
                            connectors = site["connectors"]
                            location_id = site["location_id"]
                        self._favorite_candidates = connectors
                        # Show what was resolved (site, connector count) and
                        # offer a custom name before creating the entry.
                        self._confirm_station = None
                        self._confirm_location_id = location_id
                        return await self.async_step_favorite_confirm()
                    errors[CONF_STATION_ID] = "station_not_found"
            else:
                lat = user_input[CONF_LATITUDE]
                lon = user_input[CONF_LONGITUDE]
                radius = user_input[CONF_RADIUS_KM]
                try:
                    stations = await async_fetch_stations(self.hass, lat, lon, radius)
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    stations = apply_filters(
                        stations,
                        user_input.get(CONF_MIN_POWER_KW, DEFAULT_MIN_POWER_KW),
                        user_input.get(CONF_PLUG_TYPE, FILTER_ALL),
                        FILTER_ALL,
                        FILTER_ALL,
                    )
                    if not stations:
                        errors["base"] = "no_stations_found"
                    else:
                        # Best-effort price annotation so the picker labels
                        # can show the published price after the distance.
                        price_cache = get_price_cache(self.hass)
                        await price_cache.async_ensure_fresh(self.hass)
                        annotate_prices(price_cache, stations)
                        self._favorite_candidates = stations
                        return await self.async_step_favorite_pick()

        schema = vol.Schema(
            {
                vol.Optional(CONF_STATION_ID, default=""): str,
                vol.Optional(CONF_LATITUDE, default=self.hass.config.latitude): vol.Coerce(float),
                vol.Optional(CONF_LONGITUDE, default=self.hass.config.longitude): vol.Coerce(float),
                vol.Optional(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): _RADIUS_SELECTOR,
                vol.Optional(CONF_MIN_POWER_KW, default=DEFAULT_MIN_POWER_KW): vol.Coerce(float),
                vol.Optional(CONF_PLUG_TYPE, default=FILTER_ALL): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=FILTER_ALL, label=t("option_all", self.hass)),
                            *(SelectOptionDict(value=p, label=p) for p in KNOWN_PLUG_TYPES),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                        sort=False,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="favorite", data_schema=schema, errors=errors)

    async def async_step_favorite_scope(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """The entered EvseID names one charge point at a multi-connector
        site — ask whether to pin just that charge point or the whole site."""
        site = self._pending_site
        station = self._pending_station
        if site is None or station is None:
            return await self.async_step_favorite()

        if user_input is not None:
            name = user_input.get(CONF_FAVORITE_NAME) or self._pending_name
            if user_input[CONF_FAVORITE_SCOPE] == SCOPE_SITE:
                self._favorite_candidates = site["connectors"]
                return await self._create_favorite_location_entry(site["location_id"], name)
            return await self._create_favorite_entry(station, name)

        count = site.get("count_total") or len(site["connectors"])
        schema = vol.Schema(
            {
                vol.Required(CONF_FAVORITE_SCOPE, default=SCOPE_SITE): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=SCOPE_SITE, label=t("favorite_scope_site", self.hass, count=count)
                            ),
                            SelectOptionDict(value=SCOPE_SINGLE, label=t("favorite_scope_single", self.hass)),
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(CONF_FAVORITE_NAME, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="favorite_scope",
            data_schema=schema,
            description_placeholders={
                "site": site.get("station_name") or f"{site.get('street') or ''} {site.get('city') or ''}".strip(),
                "count": str(count),
                "evse_id": station.get("evse_id") or "",
            },
        )

    async def async_step_favorite_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm an ID-resolved favorite before creating it — shows what
        was found (single charge point, or a whole site with its connector
        count) and offers an optional custom name, which the direct ID path
        otherwise never gets to ask for."""
        if self._confirm_station is None and self._confirm_location_id is None:
            return await self.async_step_favorite()

        if user_input is not None:
            name = user_input.get(CONF_FAVORITE_NAME)
            if self._confirm_station is not None:
                return await self._create_favorite_entry(self._confirm_station, name)
            return await self._create_favorite_location_entry(self._confirm_location_id, name)

        if self._confirm_station is not None:
            station = self._confirm_station
            desc_parts = [p for p in [station.get("station_name"), station.get("city")] if p]
            what = t(
                "favorite_confirm_single",
                self.hass,
                evse_id=station.get("evse_id") or "?",
                name=" · ".join(desc_parts),
            )
        else:
            location = group_by_location(self._favorite_candidates).get(self._confirm_location_id) or {}
            site_parts = [p for p in [location.get("station_name"), location.get("street"), location.get("city")] if p]
            what = t(
                "favorite_confirm_site",
                self.hass,
                name=" · ".join(site_parts) or self._confirm_location_id,
                count=location.get("count_total") or len(self._favorite_candidates),
            )

        schema = vol.Schema({vol.Optional(CONF_FAVORITE_NAME, default=""): str})
        return self.async_show_form(
            step_id="favorite_confirm",
            data_schema=schema,
            description_placeholders={"what": what},
        )

    async def async_step_favorite_pick(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Pick either a single charge point or a whole physical site (all
        its connectors together) from the nearby search results gathered in
        the previous step."""
        if user_input is not None:
            selected = user_input[CONF_STATION_ID]
            if selected.startswith(_LOCATION_PREFIX):
                return await self._create_favorite_location_entry(
                    selected[len(_LOCATION_PREFIX) :], user_input.get(CONF_FAVORITE_NAME)
                )
            station = self._favorite_candidates.get(selected)
            if station is None:
                return await self.async_step_favorite()
            return await self._create_favorite_entry(station, user_input.get(CONF_FAVORITE_NAME))

        locations = group_by_location(self._favorite_candidates)
        location_options = [
            SelectOptionDict(
                value=f"{_LOCATION_PREFIX}{location_id}", label=location_display_label(location, self.hass)
            )
            for location_id, location in sorted(locations.items(), key=lambda kv: kv[1]["distance_km"])
        ]
        connector_options = [
            SelectOptionDict(value=station_id, label=station_display_label(station, self.hass))
            for station_id, station in sorted(
                self._favorite_candidates.items(), key=lambda kv: kv[1]["distance_km"]
            )
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[*location_options, *connector_options], mode=SelectSelectorMode.DROPDOWN, sort=False
                    )
                ),
                vol.Optional(CONF_FAVORITE_NAME, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="favorite_pick",
            data_schema=schema,
            description_placeholders={"count": str(len(connector_options))},
        )

    async def _create_favorite_entry(self, station: dict, custom_name: str | None) -> FlowResult:
        evse_id = station.get("evse_id")
        if not evse_id:
            return self.async_show_form(
                step_id="favorite",
                data_schema=vol.Schema(
                    {
                        vol.Optional(CONF_STATION_ID, default=""): str,
                        vol.Optional(CONF_LATITUDE, default=self.hass.config.latitude): vol.Coerce(float),
                        vol.Optional(CONF_LONGITUDE, default=self.hass.config.longitude): vol.Coerce(float),
                        vol.Optional(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): _RADIUS_SELECTOR,
                    }
                ),
                errors={"base": "no_evse_id"},
            )

        await self.async_set_unique_id(f"favorite_{evse_id}")
        self._abort_if_unique_id_configured()

        custom_name = (custom_name or "").strip()
        name = custom_name or station.get("station_name") or station.get("city") or evse_id
        return self.async_create_entry(
            title=t("favorite_device_name", self.hass, name=name),
            data={
                CONF_ENTRY_TYPE: ENTRY_TYPE_FAVORITE,
                CONF_STATION_ID: evse_id,
                CONF_FAVORITE_NAME: custom_name or None,
            },
        )

    async def _create_favorite_location_entry(self, location_id: str, custom_name: str | None) -> FlowResult:
        location = group_by_location(self._favorite_candidates).get(location_id)

        await self.async_set_unique_id(f"favorite_location_{location_id}")
        self._abort_if_unique_id_configured()

        custom_name = (custom_name or "").strip()
        fallback = (location.get("station_name") or location.get("city") or location_id) if location else location_id
        name = custom_name or fallback
        data = {
            CONF_ENTRY_TYPE: ENTRY_TYPE_FAVORITE_LOCATION,
            CONF_STATION_LOCATION_ID: location_id,
            CONF_FAVORITE_NAME: custom_name or None,
        }
        if location and location.get("is_synthetic"):
            # No real ChargingStationId covers this site (see group_by_location) —
            # pin the member EvseIDs so the coordinator can re-fetch it later.
            data[CONF_STATION_LOCATION_EVSE_IDS] = sorted(location["connectors"])
        return self.async_create_entry(
            title=t("favorite_location_device_name", self.hass, name=name),
            data=data,
        )


class IchTankeStromOptionsFlow(OptionsFlow):
    """Configure dialog. Radius entries only: pick which plug types get a
    dedicated available-count sensor. The live filters (min power, plug type,
    status, operator) intentionally stay on their number/select entities —
    they are meant to be flipped from a dashboard, not buried in a dialog."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self.config_entry.data.get(CONF_ENTRY_TYPE, ENTRY_TYPE_RADIUS) != ENTRY_TYPE_RADIUS:
            return self.async_abort(reason="no_options")

        if user_input is not None:
            # Merge instead of replace — entry.options also carries the live
            # filter values written by the number/select entities.
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_PLUG_TYPE_SENSORS: user_input.get(CONF_PLUG_TYPE_SENSORS, []),
                }
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PLUG_TYPE_SENSORS,
                    default=list(self.config_entry.options.get(CONF_PLUG_TYPE_SENSORS) or []),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=p, label=p) for p in KNOWN_PLUG_TYPES],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        sort=False,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
