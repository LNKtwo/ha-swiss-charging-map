# Changelog

## 1.0.0 (2026-10-27)

Initial release.

- Live availability of ~19,000 Swiss public charge points from the official
  ich-tanke-strom.ch platform (BFE / EnergieSchweiz / swisstopo) — radius
  overview with map markers, favorite station/site pinning, live filters
  (minimum power, plug type, status, operator). Based on
  [prusuino/ha_swiss_charging_stations](https://github.com/prusuino/ha_swiss_charging_stations)
  v1.11.0 (MIT).
- **New:** optional Chargeprice price layer — structured min/max CHF/kWh per
  station (marker attributes) and a "cheapest charger in radius" sensor.
  Needs a free Chargeprice API key (demo access, non-commercial); without a
  key the integration runs exactly like upstream, including the BFE ad-hoc
  price atlas (prices.py, no key required).
- Integration renamed: domain `ich_tanke_strom` → `swiss_charging_map`.
