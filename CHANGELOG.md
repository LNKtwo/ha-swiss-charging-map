# Changelog

## 1.0.3 (2026-10-28)

- **Fix:** charge points published twice by different data feeds (same
  EvseID, e.g. Mall of Switzerland via MOVE and Energie 360°) are no longer
  shown twice, and the copy with live status wins over the one reporting
  "Unknown". Affected the map counts, single and site favorites, and site
  resolution during setup.

## 1.0.2 (2026-10-28)

- **New:** the "cheapest price" sensor works without an API key — it falls
  back to the energy component of the BFE ad-hoc atlas price (e.g. 0.49 from
  "0.49 CHF/kWh + 0.25 CHF/Min (> 1h)"). Attributes `price_source`
  (`chargeprice` / `bfe`) and `price_text` (full published price) show where
  the value comes from and any time or session fees it excludes.
- **New:** map markers expose `price_kwh`, the atlas price as a number.
- **New:** the Chargeprice API key, currency and match radius can be set or
  changed in the integration's Configure dialog — no need to re-add the entry.

## 1.0.1 (2026-10-28)

- **Fix:** Chargeprice prices are now kept per search area — with several
  radius entries, only the first entry's area used to get prices.
- **Fix:** a tariff without any price no longer aborts the whole Chargeprice
  refresh (`ValueError` in the tariff summary).
- **Fix:** a single HTTP 429 no longer disables the Chargeprice layer until
  Home Assistant restarts; it now retries in the next batch window.
- **Fix:** Chargeprice coverage grows over time — each hourly batch prices the
  nearest stations that are still unpriced or stale, instead of re-pricing
  the same first 30 stations forever.
- **Fix:** Chargeprice requests now use a timeout, so a hanging API can no
  longer stall the availability refresh.
- **Fix:** the distance fallback for joining Chargeprice prices was never
  used; it now matches stations within the configured match radius.
- **Fix:** "Cheapest price" sensor attributes `station`, `distance_km` and
  `max_power_kw` were always empty; its unit follows the configured currency.

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
