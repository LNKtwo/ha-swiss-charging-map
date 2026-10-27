"""Geo-location entities for charging sites.

Radius entries only: shows one marker per physical charging site (connectors
grouped by ChargingStationId / operator+address, same grouping as the
favorite picker) that currently matches the live filters. The marker label
carries the site's availability ("6/7 frei"), so multi-connector sites no
longer stack several indistinguishable per-connector markers on identical
coordinates. Custom lightweight management instead of an external
feed-manager package — on every coordinator update (new data OR a filter
change), the currently filtered site list is diffed against the entities
already created (new ones added, stale ones removed, surviving ones updated
in place so their label stays current).

Favorite entries (single connector or whole site) intentionally get no map
marker — the radius view already covers map display, and a favorite is
tracked via its sensors instead.
"""
from __future__ import annotations

import logging

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MAX_MAP_MARKERS
from .coordinator import IchTankeStromCoordinator, icon_for_status, site_status
from .localization import localized_site_status, localized_status, t

_LOGGER = logging.getLogger(__name__)
SOURCE = "swiss_charging_map"
ATTRIBUTION = "Data: ich-tanke-strom.ch (BFE / EnergieSchweiz / swisstopo)"

_UNIQUE_ID_PREFIX = f"{DOMAIN}_loc_"


def _entry_unique_id_prefix(entry_id: str) -> str:
    """Unique-id prefix of one config entry's markers. The entry id is part of
    it so two radius entries covering the same site (a home and a work radius
    that overlap) each get their own marker instead of fighting over one
    registry entry — Home Assistant refuses the second as a duplicate id and
    the site silently goes missing from that entry's map."""
    return f"{_UNIQUE_ID_PREFIX}{entry_id}_"


def _migrate_marker_registry(registry: er.EntityRegistry, entry_id: str) -> None:
    """One-time registry maintenance for this entry's map markers, run before
    the first marker is added so nothing gets registered twice:

    - Markers used to be one per connector (unique id without the _loc_
      prefix). Their registry entries would otherwise linger as unavailable
      orphans after the switch to per-site markers, so they are removed.
    - Per-site markers used to be keyed by the site id alone (see
      _entry_unique_id_prefix). Those are migrated in place to the
      entry-scoped id, so the entity id, its history and whatever the user
      changed on it (name, visibility, area) survive.

    Only registry entries belonging to this config entry are touched.
    """
    entry_prefix = _entry_unique_id_prefix(entry_id)
    for reg_entry in er.async_entries_for_config_entry(registry, entry_id):
        if reg_entry.domain != "geo_location":
            continue
        unique_id = reg_entry.unique_id
        if not unique_id.startswith(_UNIQUE_ID_PREFIX):
            registry.async_remove(reg_entry.entity_id)
            continue
        if unique_id.startswith(entry_prefix):
            continue
        new_unique_id = f"{entry_prefix}{unique_id[len(_UNIQUE_ID_PREFIX):]}"
        if registry.async_get_entity_id("geo_location", DOMAIN, new_unique_id):
            # The migrated twin already exists (an earlier run was cut short
            # by an error) — this one would only be a duplicate now.
            registry.async_remove(reg_entry.entity_id)
            continue
        registry.async_update_entity(reg_entry.entity_id, new_unique_id=new_unique_id)
        _LOGGER.debug("Migrated map marker %s to the entry-scoped unique id", reg_entry.entity_id)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: IchTankeStromCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_entities: dict[str, ChargingSiteEvent] = {}

    # Before the first marker is added, so nothing gets registered twice.
    _migrate_marker_registry(er.async_get(hass), entry.entry_id)

    @callback
    def _sync_entities() -> None:
        # Runs on every coordinator notification — including a failed
        # refresh, which keeps the previous data but flips
        # last_update_success. The in-place update below then writes state
        # for every surviving marker, which is what publishes the
        # availability change (see ChargingSiteEvent.available).
        locations = (coordinator.data or {}).get("filtered_locations", {})

        if len(locations) > MAX_MAP_MARKERS:
            # A big radius can match thousands of sites — creating a map
            # marker for each would overwhelm Home Assistant. Keep the
            # nearest ones; the count sensor still covers the full set.
            nearest = sorted(locations.items(), key=lambda kv: kv[1].get("distance_km") or 0)
            locations = dict(nearest[:MAX_MAP_MARKERS])
            _LOGGER.info(
                "Radius matches %d charging sites — showing only the nearest %d on the map",
                len(nearest),
                MAX_MAP_MARKERS,
            )

        new_entities = []
        for location_id, location in locations.items():
            existing = known_entities.get(location_id)
            if existing is None:
                known_entities[location_id] = ChargingSiteEvent(
                    hass, coordinator, entry.entry_id, location_id, location
                )
                new_entities.append(known_entities[location_id])
            else:
                existing.update_location(location)
        if new_entities:
            async_add_entities(new_entities)

        for location_id in [e for e in known_entities if e not in locations]:
            entity = known_entities.pop(location_id)
            # Only the entity is removed; its registry row is kept on
            # purpose. A site leaves the filtered set as easily as it joins
            # it (a filter change, a connector going out of service), and
            # when it comes back the row hands it the same entity id, its
            # history, and whatever the user changed on it — a rename, an
            # area, the visibility flag. The per-plug-type sensors in
            # sensor.py do drop their row, but there the user deselected the
            # sensor deliberately in the Configure dialog.
            hass.async_create_task(entity.async_remove(force_remove=True))

    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))
    _sync_entities()


class ChargingSiteEvent(GeolocationEvent):
    """One physical charging site (all its connectors combined). Lifecycle
    (appearing/disappearing) is managed by the sync function above; label
    and attributes are refreshed in place on every coordinator update, and
    availability follows the coordinator's last refresh."""

    _attr_should_poll = False
    _attr_source = SOURCE
    _attr_attribution = ATTRIBUTION
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_has_entity_name = False
    # Hidden from Home Assistant's auto-generated default dashboard map (which
    # otherwise draws every geo_location entity in the system) — still shown
    # on a Map card that references them by source, which does not go through
    # the visible-by-default list. This applies to entities registered for the
    # first time; whether an existing entity stays hidden is the user's
    # decision alone and is never rewritten from here.
    _attr_entity_registry_visible_default = False

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: IchTankeStromCoordinator,
        entry_id: str,
        location_id: str,
        location: dict,
    ) -> None:
        self._hass_ref = hass
        self._coordinator = coordinator
        self._location = location
        self._attr_unique_id = f"{_entry_unique_id_prefix(entry_id)}{location_id}"

        name = location.get("station_name") or location.get("city") or t("station_fallback_name", hass)
        max_power = self._max_power_kw(location)
        power_text = f"{max_power:g}kW " if max_power else ""
        prefix = t("station_entity_prefix", hass)
        self._attr_name = f"{prefix} {power_text}– {name}"
        self._attr_latitude = location.get("latitude")
        self._attr_longitude = location.get("longitude")
        self._attr_distance = location.get("distance_km")

    @callback
    def update_location(self, location: dict) -> None:
        """Refresh availability/attributes in place on a coordinator update,
        so the map label stays current without recreating the entity."""
        self._location = location
        self._attr_distance = location.get("distance_km")
        if self.hass:
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Like the sensors: while the source is unreachable the marker is
        unavailable instead of showing its last known label indefinitely.
        Not a CoordinatorEntity (the lifecycle is managed by the sync
        function), so this reads the coordinator directly; the sync function
        writes state after every refresh, failed ones included, so a flip
        reaches the state machine."""
        return self._coordinator.last_update_success

    @staticmethod
    def _max_power_kw(location: dict) -> float:
        return max(
            ((c.get("power_kw") or 0) for c in location.get("connectors", {}).values()),
            default=0,
        )

    def _status_label(self) -> str:
        """The map-marker label: a single connector shows its plain status,
        a multi-connector site shows availability as "free/total" — or the
        derived site status when nothing is in service ("closed" for a
        non-24h site outside opening hours, "out of service" otherwise)."""
        location = self._location
        connectors = location.get("connectors", {})
        if len(connectors) <= 1:
            only = next(iter(connectors.values()), {})
            if only.get("status") == "OutOfService" and not location.get("open_24h"):
                return localized_site_status("closed", self._hass_ref)
            return localized_status(only.get("status"), self._hass_ref)
        status = site_status(location)
        if status in ("closed", "out_of_service"):
            return localized_site_status(status, self._hass_ref)
        return t(
            "map_label_free",
            self._hass_ref,
            free=location.get("count_available", 0),
            total=location.get("count_total", len(connectors)),
        )

    @property
    def icon(self):
        if self._location.get("count_available", 0) > 0:
            return icon_for_status("Available")
        connectors = self._location.get("connectors", {})
        statuses = {c.get("status") for c in connectors.values()}
        if statuses == {"OutOfService"}:
            return icon_for_status("OutOfService")
        if "Occupied" in statuses:
            return icon_for_status("Occupied")
        return icon_for_status(None)

    @property
    def extra_state_attributes(self):
        location = self._location
        connectors = location.get("connectors", {})
        plug_types = sorted({p for c in connectors.values() for p in (c.get("plugs") or [])})
        return {
            # Localized for display (used as the map marker label via
            # label_mode: attribute). Filtering uses the raw API values
            # internally in the coordinator, unaffected by this.
            "status": self._status_label(),
            "count_available": location.get("count_available", 0),
            "count_total": location.get("count_total", len(connectors)),
            "max_power_kw": self._max_power_kw(location),
            "plug_types": plug_types,
            "operator": location.get("operator") or t("unknown_operator", self._hass_ref),
            "street": location.get("street"),
            "city": location.get("city"),
            "postal_code": location.get("postal_code"),
            "open_24h": location.get("open_24h"),
            # Published ad-hoc price ("0.57 CHF/kWh"), None for operators
            # that publish none — see prices.py.
            "price": location.get("price"),
            # Structured prices from the optional Chargeprice layer
            # (chargeprice.py) — CHF/kWh, None when the layer is off or the
            # operator publishes nothing there.
            "price_min": location.get("price_min"),
            "price_max": location.get("price_max"),
            "price_provider": location.get("price_provider"),
        }
