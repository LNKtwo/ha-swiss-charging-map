"""Constants for the ich-tanke-strom.ch integration."""
DOMAIN = "swiss_charging_map"

# Plain HTTP, deliberately: the GeoServer behind ich-tanke-strom.ch offers no
# TLS listener on any port — https:// on 8080 or 443 is refused, so there is
# no secure variant of this endpoint to switch to. The data is public,
# read-only and carries no credentials: the request sends no token, no
# cookie and nothing about the user beyond the queried bounding box, so a
# passive observer learns only the rough area someone is looking at. The URL
# is defined here rather than built at call time so this stays reviewable in
# one place; if the operator ever adds TLS, this single line is the change.
WFS_URL = "http://ich-tanke-strom.switzerlandnorth.cloudapp.azure.com:8080/geoserver/ich-tanke-strom/ows"
KM_PER_DEGREE = 111.0
UPDATE_INTERVAL_MINUTES = 5

# Large radii return large result sets: measured 2026-07-17, a 50 km radius
# yields ~6,000 features and took ~38 s / 6.7 MB unslimmed — well past the old
# 30 s timeout, which made setup fail entirely. The radius fetch therefore
# requests only the needed properties (roughly halves size and time) and uses
# a generous timeout.
FETCH_TIMEOUT_SECONDS = 90

# Cap on map markers created by one radius entry. Without it, a big radius
# floods Home Assistant with thousands of geo_location entities (websocket
# overload, sluggish frontend). The nearest stations win; the count sensor
# still reflects the full filtered set.
MAX_MAP_MARKERS = 500

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_KM = "radius_km"

DEFAULT_RADIUS_KM = 15

# Upper bound for the radius, enforced in the config flow and documented in
# the README. Beyond this the source server needs 20-40+ s per fetch and the
# result set grows into thousands of stations — measured 2026-07-17: 15 km ≈
# 600 stations / 3 s, 50 km ≈ 6,000 stations / 38 s.
MAX_RADIUS_KM = 30

# --- Chargeprice price layer (chargeprice.py) — optional, needs an API key.
# Free demo keys (non-commercial): https://insights.chargeprice.app/signup?demo=true
CONF_CHARGEPRICE_API_KEY = "chargeprice_api_key"
CONF_CHARGEPRICE_CURRENCY = "chargeprice_currency"
CONF_PRICE_MATCH_RADIUS_M = "price_match_radius_m"
DEFAULT_CHARGEPRICE_CURRENCY = "CHF"
DEFAULT_PRICE_MATCH_RADIUS_M = 150
CHARGEPRICE_API_URL = "https://api.chargeprice.app/v1"
CHARGEPRICE_TIMEOUT_SECONDS = 30
# Demo keys are rate-limited hard: at most this many stations are priced per
# batch, at most one batch per search area every
# CHARGEPRICE_BATCH_INTERVAL_MINUTES; results are cached PRICE_MAX_AGE_HOURS.
CHARGEPRICE_MAX_STATIONS_PER_CYCLE = 30
CHARGEPRICE_BATCH_INTERVAL_MINUTES = 60
CHARGEPRICE_SESSION_ENERGY_KWH = 30.0
CHARGEPRICE_SESSION_MINUTES = 30.0
CHARGEPRICE_SESSION_START_MINUTES = 720
# Cache lifetime of both price layers (prices.py and chargeprice.py).
PRICE_MAX_AGE_HOURS = 6

# Which kind of config entry this is. Radius entries (the original/default
# kind) show every station within a live-filterable area. Favorite entries
# pin exactly one specific station, independent of any location/radius —
# added again, once per favorite, same as radius entries are added again for
# a different area. Entries created before this distinction existed have no
# CONF_ENTRY_TYPE key at all; treat that as ENTRY_TYPE_RADIUS (the only kind
# that used to exist), never write a migration-required default for it.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_RADIUS = "radius"
ENTRY_TYPE_FAVORITE = "favorite"
ENTRY_TYPE_FAVORITE_LOCATION = "favorite_location"

# Favorite-specific config keys.
CONF_STATION_ID = "station_id"  # the station's EvseID — stable, queryable, independent of the opaque WFS feature id used to key the radius view's stations dict
CONF_FAVORITE_NAME = "favorite_name"

# Favorite-location-specific config key. A "location" groups every charge
# point (EVSE) sharing the same ChargingStationId — many real charging sites
# have several connectors that all sit at identical GPS coordinates, so
# favoriting/mapping them individually produces stacked, indistinguishable
# markers. A location favorite is one device with one summary sensor and one
# map marker for the whole site instead.
CONF_STATION_LOCATION_ID = "station_location_id"

# Set only for a location favorite whose group was formed by the address
# fallback (see group_by_location) instead of a real shared ChargingStationId
# — there is no single ID the API understands to re-fetch the site, so the
# member EvseIDs are pinned explicitly and refreshed by EvseID instead.
CONF_STATION_LOCATION_EVSE_IDS = "station_location_evse_ids"

# Options (live-adjustable filters, stored in entry.options).
CONF_MIN_POWER_KW = "min_power_kw"
CONF_PLUG_TYPE = "plug_type"
CONF_STATUS = "status"
CONF_OPERATOR = "operator"

DEFAULT_MIN_POWER_KW = 0.0

# Canonical (language-independent) values stored in entry.options. The
# user-facing labels for these are resolved via localization.py at render
# time, so filtering logic never depends on the active HA language.
FILTER_ALL = "__all__"
STATUS_AVAILABLE = "available"
STATUS_OCCUPIED = "occupied"

# Known plug types reported by the API — used as a filter on the favorite
# station search form, chosen upfront before searching (the full list can't
# be known before a fetch). Matches the API's own literal string values
# exactly, since filtering must match raw strings, not a translated label.
# Verified against a near-complete national query (18,881 of ~19,000
# stations) on 2026-07-17 — these 8 are the only values that actually occur.
KNOWN_PLUG_TYPES = [
    "CCS Combo 1 Plug (Cable Attached)",
    "CCS Combo 2 Plug (Cable Attached)",
    "CHAdeMO",
    "Tesla Connector",
    "Type 1 Connector (Cable Attached)",
    "Type 2 Connector (Cable Attached)",
    "Type 2 Outlet",
    "Type J Swiss Standard",
]

# Option (set via the integration's Configure dialog): plug types that get
# their own dedicated available-count sensor on a radius entry. Stored as a
# list of raw API plug type strings. These sensors ignore the live plug-type
# and status filters (which only shape the map/count sensor), so their
# meaning stays stable while the map is being filtered.
CONF_PLUG_TYPE_SENSORS = "plug_type_sensors"

# Compact entity_id suffix per plug type — the raw API strings are far too
# long for entity ids ("CCS Combo 2 Plug (Cable Attached)").
PLUG_TYPE_SLUGS = {
    "CCS Combo 1 Plug (Cable Attached)": "ccs1",
    "CCS Combo 2 Plug (Cable Attached)": "ccs2",
    "CHAdeMO": "chademo",
    "Tesla Connector": "tesla",
    "Type 1 Connector (Cable Attached)": "type1",
    "Type 2 Connector (Cable Attached)": "type2_cable",
    "Type 2 Outlet": "type2_outlet",
    "Type J Swiss Standard": "type_j",
}

# Short display label per plug type, used in sensor names. Language-neutral
# on purpose — raw plug type strings are shown untranslated everywhere else
# in this integration (select options, attributes) as documented in select.py.
PLUG_TYPE_SHORT_LABELS = {
    "CCS Combo 1 Plug (Cable Attached)": "CCS Combo 1",
    "CCS Combo 2 Plug (Cable Attached)": "CCS Combo 2",
    "CHAdeMO": "CHAdeMO",
    "Tesla Connector": "Tesla",
    "Type 1 Connector (Cable Attached)": "Type 1",
    "Type 2 Connector (Cable Attached)": "Type 2 (Cable)",
    "Type 2 Outlet": "Type 2 (Outlet)",
    "Type J Swiss Standard": "Type J",
}
