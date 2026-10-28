# Swiss Charging Map — Die ultimative Schweizer Ladekarte

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/LICENSE-blue.svg)](LICENSE)

Live-Verfügbarkeit **und** Preise der öffentlichen Schweizer Ladeinfrastruktur in Home Assistant — auf einer Karte.

- **Ladestationen:** ~19'000 öffentliche Ladepunkte der offiziellen Plattform [ich-tanke-strom.ch](https://www.ich-tanke-strom.ch) (BFE / EnergieSchweiz / swisstopo) — mit **Live-Status** (frei / belegt / ausser Betrieb), alle 5 Minuten aktualisiert.
- **Ad-hoc-Preise inklusive:** Der Bundes-Ladepreisatlas (Swiss eMobility via data.geo.admin.ch) liefert für betreiberveröffentlichte Stationen den Ad-hoc-Preis („0.57 CHF/kWh") — **ohne Registrierung, ohne API-Key.**
- **Optional: Chargeprice-Layer** — mit einem kostenlosen API-Key ergänzt die Integration strukturierte Min./Max.-Preise (CHF/kWh) für die grosse Mehrheit aller Schweizer Stationen (Swisscharge, MOVE/JOYA, GOFAST, Agrola, Migrol, IONITY u.v.m.) plus einen „Günstigster Ladepunkt im Umkreis"-Sensor.

## Features

| Bereich | Beschreibung |
|---|---|
| Radius-Übersicht | Jede passende Ladestelle als Karten-Marker mit Live-Verfügbarkeit im Label („6/7 frei"), Distanz als Entitäts-State |
| Live-Filter | Mindestleistung (kW), Steckertyp (CCS/Typ 2/CHAdeMO …), Status und Betreiber — als `number`/`select`-Entitäten, wirken sofort |
| Verfügbarkeits-Sensor | Freie Stationen im Umkreis, gesamt + pro Steckertyp, Betreiber-Liste in den Attributen |
| Favoriten | Einzelne Ladepunkte oder ganze Ladestandorte pinnbar — unabhängig von Radius/Standort, wiederholbar |
| Preise (BFE-Atlas) | Ad-hoc-Preis pro Station, ohne Key (Abdeckung ~25 % der Standorte) |
| Preise (Chargeprice, optional) | Strukturierte min/max CHF/kWh pro Station + „Günstigster Ladepunkt im Umkreis"-Sensor (Abdeckung deutlich höher; eigener kostenloser Demo-Key nötig) |

## Installation

### HACS (empfohlen)

1. HACS → ⋮ → **Benutzerdefiniertes Repository hinzufügen**
2. Repository-URL: `https://github.com/LNKtwo/ha-swiss-charging-map`, Kategorie: **Integration**
3. **Swiss Charging Map** installieren, Home Assistant neu starten

### Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Swiss Charging Map"**
2. Modus **Radius-Übersicht** wählen; Breite/Länge (Default: Home-Standort) und Radius (max. 30 km) setzen
3. **Optional — Preis-Layer:** Chargeprice-API-Key eintragen (kostenloser Demo-Key, nicht-kommerziell: [insights.chargeprice.app/signup?demo=true](https://insights.chargeprice.app/signup?demo=true)). Währung (Standard CHF) und Preis-Abgleichsradius (Standard 150 m) passen in der Regel.
4. Filter (Mindest-kW, Steckertyp, Status, Betreiber) danach live über die `number`/`select`-Entitäten stellen — ohne Neustart.
5. Favoriten: Integration erneut hinzufügen → „Favorit" — per EvseID oder Umgebungssuche.

## Karten-Beispiel

```yaml
type: map
geo_location_sources:
  - source: swiss_charging_map
    label_mode: attribute
    attribute: price_min
```

Marker-Attribute (pro Station): `price` (BFE-Ad-hoc-Preis), `price_min`/`price_max`/`price_provider` (Chargeprice-Layer), `count_available`/`count_total`, `max_power_kw`, `plug_types`, `operator`, `street`, `city`, `status`.

Marker **nicht** über Entity-IDs ansprechen (die Namen sind lokalisiert) — immer `geo_location_sources` mit `source: swiss_charging_map` nutzen oder nach `source`-Attribut filtern.

## Preis-Quellen & Grenzen

| Quelle | Key nötig | Abdeckung | Beschreibung |
|---|---|---|---|
| BFE-Ladepreisatlas (via data.geo.admin.ch) | Nein | ~25 % der Standorte | Ad-hoc-Preis als Text, immer ohne Abo (walk-up) |
| Chargeprice-API (optional) | Ja (kostenloser Demo-Key) | Grossmehrteil der Schweizer Netze | Strukturiert min/max CHF/kWh; Direct-Payment-Tarife bevorzugt; Demo-Limit: max. 30 Stationen pro Stunde und Suchgebiet, 6 h Cache |

Beide Quellen ergänzen sich: der Ad-hoc-Atlas ist keyless, Chargeprice liefert Breite + Struktur. Ohne Key verhält sich die Integration identisch zum Upstream.

**Demo-Key-Hinweis:** Der Chargeprice-Demo-Zugang ist für nicht-kommerzielle Nutzung bestimmt und stark ratenlimitiert — deshalb preist die Integration pro Stunde und Suchgebiet maximal 30 Stationen (die nächstgelegenen noch ungepreisten zuerst, die Abdeckung wächst also schrittweise) und cached die Preise 6 Stunden.

## Credits

- Basis: [prusuino/ha_swiss_charging_stations](https://github.com/prusuino/ha_swiss_charging_stations) v1.11.0 (MIT) — die hervorragende ich-tanke-strom.ch-Integration, von der dieser Fork seinen Live-Daten-Layer übernimmt.
- Stationsdaten: [ich-tanke-strom.ch](https://www.ich-tanke-strom.ch) — BFE / EnergieSchweiz / swisstopo
- Ad-hoc-Preise: Ladepreisatlas Swiss eMobility (chargeprice.app) via BFE / data.geo.admin.ch
- Optionale Preisdaten: [Chargeprice](https://www.chargeprice.app) API

## Lizenz

[MIT](LICENSE) — © prusuino (Basis) & Onur Iriz (Swiss Charging Map)

---

**English summary:** Home Assistant custom integration showing real-time availability *and* prices of Swiss public EV charging stations. Live data from the official ich-tanke-strom.ch platform (BFE/swisstopo): radius overview with map markers, live filters (min power / plug type / status / operator), favorite station pinning. Prices: federal ad-hoc price atlas out of the box (no key), optional Chargeprice layer (free demo key) adding structured min/max CHF/kWh per station and a cheapest-charger-in-radius sensor. Install via HACS as a custom repository. MIT licensed, based on prusuino's ha_swiss_charging_stations.
