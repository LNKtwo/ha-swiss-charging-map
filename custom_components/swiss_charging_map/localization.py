"""Runtime string localization (entity names, card content, select options).

Home Assistant's built-in translation system (strings.json / translations/*.json)
only covers config/options flow text. Entity names, card content, and select
option values are set directly by this integration's Python code and
are not covered by that mechanism, so we do our own minimal lookup here, keyed
by hass.config.language. Falls back to English for any language we don't have
strings for.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

SUPPORTED_LANGUAGES = ("de", "en", "fr", "it")

STRINGS: dict[str, dict[str, str]] = {
    "device_name": {
        "de": "Ladestationen Schweiz (Umkreis {radius} km)",
        "en": "Charging Stations Switzerland (Radius {radius} km)",
        "fr": "Bornes de recharge Suisse (Rayon {radius} km)",
        "it": "Stazioni di ricarica Svizzera (Raggio {radius} km)",
    },
    "cheapest_charger_name": {
        "de": "Ladestationen Günstigster Preis",
        "en": "Charging Stations Cheapest Price",
        "fr": "Bornes de recharge prix le plus bas",
        "it": "Stazioni di ricarica prezzo più basso",
    },
    "min_power_name": {
        "de": "Ladestationen Mindestleistung",
        "en": "Charging Stations Minimum Power",
        "fr": "Bornes de recharge puissance minimale",
        "it": "Stazioni di ricarica potenza minima",
    },
    "plug_type_name": {
        "de": "Ladestationen Steckertyp",
        "en": "Charging Stations Plug Type",
        "fr": "Bornes de recharge type de connecteur",
        "it": "Stazioni di ricarica tipo di connettore",
    },
    "status_name": {
        "de": "Ladestationen Status",
        "en": "Charging Stations Status",
        "fr": "Bornes de recharge statut",
        "it": "Stazioni di ricarica stato",
    },
    "operator_name": {
        "de": "Ladestationen Betreiber",
        "en": "Charging Stations Operator",
        "fr": "Bornes de recharge exploitant",
        "it": "Stazioni di ricarica gestore",
    },
    "option_all": {
        "de": "Alle",
        "en": "All",
        "fr": "Tous",
        "it": "Tutti",
    },
    "status_available_only": {
        "de": "Nur freie",
        "en": "Available only",
        "fr": "Disponibles uniquement",
        "it": "Solo disponibili",
    },
    "status_occupied_only": {
        "de": "Nur besetzte",
        "en": "Occupied only",
        "fr": "Occupées uniquement",
        "it": "Solo occupate",
    },
    "sensor_free_name": {
        "de": "Ladestationen frei",
        "en": "Charging Stations Free",
        "fr": "Bornes de recharge libres",
        "it": "Stazioni di ricarica libere",
    },
    "sensor_free_plug_name": {
        "de": "Ladestationen frei {plug}",
        "en": "Charging Stations Free {plug}",
        "fr": "Bornes de recharge libres {plug}",
        "it": "Stazioni di ricarica libere {plug}",
    },
    "station_entity_prefix": {
        "de": "Ladestation",
        "en": "Charging Station",
        "fr": "Borne de recharge",
        "it": "Stazione di ricarica",
    },
    "map_label_free": {
        "de": "{free}/{total} frei",
        "en": "{free}/{total} available",
        "fr": "{free}/{total} libres",
        "it": "{free}/{total} liberi",
    },
    "station_fallback_name": {
        "de": "Ladestation",
        "en": "Charging station",
        "fr": "Borne de recharge",
        "it": "Stazione di ricarica",
    },
    "unknown_operator": {
        "de": "Unbekannt",
        "en": "Unknown",
        "fr": "Inconnu",
        "it": "Sconosciuto",
    },
    "status_available": {
        "de": "Frei",
        "en": "Available",
        "fr": "Disponible",
        "it": "Disponibile",
    },
    "status_occupied": {
        "de": "Besetzt",
        "en": "Occupied",
        "fr": "Occupée",
        "it": "Occupata",
    },
    "status_out_of_service": {
        "de": "Ausser Betrieb",
        "en": "Out of service",
        "fr": "Hors service",
        "it": "Fuori servizio",
    },
    "status_unknown": {
        "de": "Unbekannt",
        "en": "Unknown",
        "fr": "Inconnu",
        "it": "Sconosciuto",
    },
    "site_status_closed": {
        "de": "Geschlossen",
        "en": "Closed",
        "fr": "Fermée",
        "it": "Chiusa",
    },
    "mode_radius": {
        "de": "Umkreis-Übersicht (mehrere Stationen, Live-Filter)",
        "en": "Radius overview (multiple stations, live filters)",
        "fr": "Aperçu par rayon (plusieurs bornes, filtres en direct)",
        "it": "Panoramica per raggio (più stazioni, filtri live)",
    },
    "mode_favorite": {
        "de": "Einzelne Station oder Standort favorisieren",
        "en": "Pin a single station or location",
        "fr": "Épingler une seule borne ou un site favori",
        "it": "Aggiungi una singola stazione o sede preferita",
    },
    "favorite_device_name": {
        "de": "Ladestation {name}",
        "en": "Charging Station {name}",
        "fr": "Borne de recharge {name}",
        "it": "Stazione di ricarica {name}",
    },
    "favorite_status_name": {
        "de": "Status",
        "en": "Status",
        "fr": "Statut",
        "it": "Stato",
    },
    "favorite_power_name": {
        "de": "Ladeleistung",
        "en": "Charging Power",
        "fr": "Puissance de charge",
        "it": "Potenza di ricarica",
    },
    "favorite_plug_type_name": {
        "de": "Steckertyp",
        "en": "Plug Type",
        "fr": "Type de connecteur",
        "it": "Tipo di connettore",
    },
    "favorite_operator_name": {
        "de": "Betreiber",
        "en": "Operator",
        "fr": "Exploitant",
        "it": "Gestore",
    },
    "favorite_station_id_name": {
        "de": "Station-ID",
        "en": "Station ID",
        "fr": "ID de la borne",
        "it": "ID stazione",
    },
    "favorite_pick_label": {
        "de": "{name} · {power:g}kW · {distance}km · {status}",
        "en": "{name} · {power:g}kW · {distance}km · {status}",
        "fr": "{name} · {power:g}kW · {distance}km · {status}",
        "it": "{name} · {power:g}kW · {distance}km · {status}",
    },
    "favorite_location_device_name": {
        "de": "Ladestandort {name}",
        "en": "Charging Site {name}",
        "fr": "Site de recharge {name}",
        "it": "Sito di ricarica {name}",
    },
    "favorite_location_pick_label": {
        "de": "📍 {name} ({count} Ladepunkte) · {distance}km",
        "en": "📍 {name} ({count} charge points) · {distance}km",
        "fr": "📍 {name} ({count} points de charge) · {distance}km",
        "it": "📍 {name} ({count} punti di ricarica) · {distance}km",
    },
    "favorite_location_available_name": {
        "de": "Freie Ladepunkte",
        "en": "Available Charge Points",
        "fr": "Points de charge disponibles",
        "it": "Punti di ricarica disponibili",
    },
    "favorite_location_available_plug_name": {
        "de": "Freie Ladepunkte {plug}",
        "en": "Available Charge Points {plug}",
        "fr": "Points de charge disponibles {plug}",
        "it": "Punti di ricarica disponibili {plug}",
    },
    "favorite_location_connector_prefix": {
        "de": "Ladepunkt {n}",
        "en": "Charge Point {n}",
        "fr": "Point de charge {n}",
        "it": "Punto di ricarica {n}",
    },
    "favorite_scope_site": {
        "de": "Ganzen Standort favorisieren ({count} Ladepunkte)",
        "en": "Favorite the whole site ({count} charge points)",
        "fr": "Ajouter tout le site aux favoris ({count} points de charge)",
        "it": "Aggiungi l'intero sito ai preferiti ({count} punti di ricarica)",
    },
    "favorite_scope_single": {
        "de": "Nur diesen einen Ladepunkt favorisieren",
        "en": "Favorite only this single charge point",
        "fr": "Ajouter uniquement ce point de charge aux favoris",
        "it": "Aggiungi solo questo punto di ricarica ai preferiti",
    },
    "favorite_confirm_single": {
        "de": "Ladepunkt {evse_id} ({name})",
        "en": "Charge point {evse_id} ({name})",
        "fr": "Point de charge {evse_id} ({name})",
        "it": "Punto di ricarica {evse_id} ({name})",
    },
    "favorite_confirm_site": {
        "de": "Standort {name} mit {count} Ladepunkten",
        "en": "Site {name} with {count} charge points",
        "fr": "Site {name} avec {count} points de charge",
        "it": "Sito {name} con {count} punti di ricarica",
    },
    "opening_24h": {
        "de": "24 h geöffnet",
        "en": "Open 24 h",
        "fr": "Ouvert 24 h/24",
        "it": "Aperto 24 ore su 24",
    },
    "accessibility_free": {
        "de": "Frei zugänglich",
        "en": "Publicly accessible",
        "fr": "Accès libre",
        "it": "Accesso libero",
    },
    "accessibility_restricted": {
        "de": "Zugang eingeschränkt",
        "en": "Restricted access",
        "fr": "Accès restreint",
        "it": "Accesso limitato",
    },
    "accessibility_paying": {
        "de": "Zugang kostenpflichtig",
        "en": "Paid access",
        "fr": "Accès payant",
        "it": "Accesso a pagamento",
    },
    "opening_unknown": {
        "de": "Unbekannt",
        "en": "Unknown",
        "fr": "Inconnu",
        "it": "Sconosciuto",
    },
    "favorite_price_name": {
        "de": "Preis",
        "en": "Price",
        "fr": "Prix",
        "it": "Prezzo",
    },
    "price_unknown": {
        "de": "Keine Angabe",
        "en": "Not published",
        "fr": "Non communiqué",
        "it": "Non pubblicato",
    },
}

# Maps the raw EvseStatus values from the ich-tanke-strom.ch API to a
# localization.py string key. The raw value is still used internally for
# filtering (language-independent); this mapping is only for display.
STATUS_KEY_MAP: dict[str, str] = {
    "Available": "status_available",
    "Occupied": "status_occupied",
    "OutOfService": "status_out_of_service",
    "Unknown": "status_unknown",
}


# Weekday abbreviations, index 0 = Monday (matching coordinator.API_WEEKDAYS).
WEEKDAYS_SHORT = {
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "fr": ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"],
    "it": ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
}


def weekday_short(index: int, hass: HomeAssistant) -> str:
    return WEEKDAYS_SHORT[get_language(hass)][index]


def get_language(hass: HomeAssistant) -> str:
    lang = (hass.config.language or "en").lower().split("-")[0]
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def t(key: str, hass: HomeAssistant, **kwargs) -> str:
    """Look up a localized string by key, formatted with kwargs."""
    lang = get_language(hass)
    template = STRINGS.get(key, {}).get(lang) or STRINGS.get(key, {}).get("en") or key
    return template.format(**kwargs) if kwargs else template


def localized_status(raw_status: str | None, hass: HomeAssistant) -> str:
    """Translate a raw EvseStatus API value for display. Filtering logic must
    keep using the raw value — only use this for user-facing attributes."""
    key = STATUS_KEY_MAP.get(raw_status or "", "status_unknown")
    return t(key, hass)


SITE_STATUS_KEY_MAP: dict[str, str] = {
    "available": "status_available",
    "occupied": "status_occupied",
    "closed": "site_status_closed",
    "out_of_service": "status_out_of_service",
}


def localized_site_status(status: str | None, hass: HomeAssistant) -> str:
    """Display text for the derived whole-site status (see
    coordinator.site_status)."""
    key = SITE_STATUS_KEY_MAP.get(status or "", "status_unknown")
    return t(key, hass)


def _with_price(label: str, entry: dict) -> str:
    """Append the published ad-hoc price to a picker label when one exists
    ("… · 0.57 CHF/kWh"). The price text is language-neutral source data, so
    no per-language template is needed."""
    price = entry.get("price")
    return f"{label} · {price}" if price else label


def station_display_label(station: dict, hass: HomeAssistant) -> str:
    """One-line label for a station in the favorite-picker dropdown."""
    name = station.get("station_name") or station.get("city") or t("station_fallback_name", hass)
    return _with_price(
        t(
            "favorite_pick_label",
            hass,
            name=name,
            power=station.get("power_kw") or 0,
            distance=station.get("distance_km"),
            status=localized_status(station.get("status"), hass),
        ),
        station,
    )


def location_display_label(location: dict, hass: HomeAssistant) -> str:
    """One-line label for a whole physical site in the favorite-picker
    dropdown, listed alongside the individual per-connector options."""
    name = location.get("station_name") or location.get("city") or t("station_fallback_name", hass)
    return _with_price(
        t(
            "favorite_location_pick_label",
            hass,
            name=name,
            count=location.get("count_total", 0),
            distance=location.get("distance_km"),
        ),
        location,
    )


# Raw Accessibility API value -> localization key. The raw value stays in
# the attributes for automations; this mapping is only for display.
ACCESSIBILITY_KEY_MAP: dict[str, str] = {
    "Free publicly accessible": "accessibility_free",
    "Restricted access": "accessibility_restricted",
    "Paying publicly accessible": "accessibility_paying",
}


def localized_accessibility(raw: str | None, hass: HomeAssistant) -> str | None:
    """Display text for the Accessibility declaration; None when unknown."""
    key = ACCESSIBILITY_KEY_MAP.get(raw or "")
    return t(key, hass) if key else None
