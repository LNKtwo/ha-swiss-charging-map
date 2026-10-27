/* swiss-charging-stations-card — colored per-connector status boxes for a
 * favorite charging station or a whole favorite site (green = available,
 * red = occupied, gray = out of service).
 *
 * Ships with the integration, which serves this file at
 * /swiss_charging_map_files/swiss-charging-stations-card.js. Add it once as a
 * Lovelace resource (Settings → Dashboards → Resources, type "JavaScript
 * module"); the README has the steps. The same file also carries the
 * dashboard strategy at the bottom, so that one resource covers both.
 *
 * Config:
 *   type: custom:swiss-charging-stations-card
 *   entity: sensor.charging_station_favorite_location_xxx   (site summary)
 *     — or —
 *   entity: sensor.charging_station_favorite_xxx            (single station)
 *   title: optional override for the card header
 */

const STATUS_COLORS = {
  Available: "var(--success-color, #2e7d32)",
  Occupied: "var(--error-color, #c62828)",
  OutOfService: "var(--disabled-text-color, #757575)",
  // Pseudo status used while the whole site is outside its opening hours —
  // distinct from the gray "broken" look and the green/red live states.
  Closed: "var(--info-color, #1565c0)",
};
const UNKNOWN_COLOR = "var(--warning-color, #f9a825)";

const AVAILABLE_WORD = { de: "frei", en: "available", fr: "libre", it: "liberi" };

const CLOSED_TODAY_WORDS = {
  de: "Heute geschlossen",
  en: "Closed today",
  fr: "Fermé aujourd'hui",
  it: "Chiuso oggi",
};

const SITE_STATUS_WORDS = {
  closed: { de: "Geschlossen", en: "Closed", fr: "Fermée", it: "Chiusa" },
  out_of_service: {
    de: "Ausser Betrieb",
    en: "Out of service",
    fr: "Hors service",
    it: "Fuori servizio",
  },
};

const TYPE_WORD = { de: "Typ", en: "Type", fr: "Type", it: "Tipo" };
const CABLE_WORD = { de: "Kabel", en: "cable", fr: "câble", it: "cavo" };

/* Abbreviations stay short as long as they are unambiguous; only the two
 * Type-2 variants (socket vs. attached cable) need the distinction. */
function shortPlug(plug, lang) {
  if (!plug) return "";
  const type = TYPE_WORD[lang] || TYPE_WORD.en;
  if (plug.startsWith("CCS Combo 2")) return "CCS";
  if (plug.startsWith("CCS Combo 1")) return "CCS 1";
  if (plug.startsWith("CHAdeMO")) return "CHAdeMO";
  if (plug.startsWith("Tesla")) return "Tesla";
  if (plug.startsWith("Type 2 Outlet")) return `${type} 2`;
  if (plug.startsWith("Type 2 Connector"))
    return `${type} 2 ${CABLE_WORD[lang] || CABLE_WORD.en}`;
  if (plug.startsWith("Type 1")) return `${type} 1`;
  if (plug.startsWith("Type J")) return "T13";
  return plug;
}

function shortPlugs(plugs, lang) {
  if (!Array.isArray(plugs)) return "";
  const shorts = [...new Set(plugs.map((p) => shortPlug(p, lang)).filter(Boolean))];
  return shorts.join(" · ");
}

const EDITOR_LABELS = {
  entity: {
    de: "Favorit-Sensor (Standort oder einzelne Station)",
    en: "Favorite sensor (site or single station)",
    fr: "Capteur favori (site ou borne individuelle)",
    it: "Sensore preferito (sede o stazione singola)",
  },
  title: {
    de: "Titel (optional)",
    en: "Title (optional)",
    fr: "Titre (optionnel)",
    it: "Titolo (opzionale)",
  },
  plug_types: {
    de: "Sichtbare Steckertypen (leer = alle)",
    en: "Visible plug types (empty = all)",
    fr: "Types de prises visibles (vide = tous)",
    it: "Tipi di presa visibili (vuoto = tutti)",
  },
  hidden_badges: {
    de: "Badges ausblenden (leer = alle anzeigen)",
    en: "Hide badges (empty = show all)",
    fr: "Masquer les badges (vide = tout afficher)",
    it: "Nascondi badge (vuoto = mostra tutto)",
  },
};

const BADGE_LABELS = {
  availability: { de: "Frei-Badge", en: "Availability badge", fr: "Badge disponibilité", it: "Badge disponibilità" },
  accessibility: { de: "Zugangs-Badge", en: "Accessibility badge", fr: "Badge accès", it: "Badge accesso" },
  renewable: { de: "Grünstrom-Badge", en: "Renewable badge", fr: "Badge énergie verte", it: "Badge energia verde" },
};

// All plug-type values observed in the national data set — offered in the
// editor when the selected entity's own connector list isn't available yet.
const KNOWN_PLUG_TYPES = [
  "CCS Combo 1 Plug (Cable Attached)",
  "CCS Combo 2 Plug (Cable Attached)",
  "CHAdeMO",
  "Tesla Connector",
  "Type 1 Connector (Cable Attached)",
  "Type 2 Connector (Cable Attached)",
  "Type 2 Outlet",
  "Type J Swiss Standard",
];

class SwissChargingStationsCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const config = { type: "custom:swiss-charging-stations-card", ...ev.detail.value };
        if (!config.title) delete config.title;
        if (!Array.isArray(config.plug_types) || !config.plug_types.length) {
          delete config.plug_types;
        }
        if (!Array.isArray(config.hidden_badges) || !config.hidden_badges.length) {
          delete config.hidden_badges;
        }
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.appendChild(this._form);
    }
    const lang = ((this._hass.language || "en").split("-")[0]);
    this._form.hass = this._hass;
    this._form.data = {
      entity: this._config.entity || "",
      title: this._config.title || "",
      plug_types: this._config.plug_types || [],
      hidden_badges: this._config.hidden_badges || [],
    };
    // Offer only the plug types that actually exist at the selected site
    // (falling back to the full national list before an entity is picked).
    const stateObj = this._hass.states[this._config.entity];
    const sitePlugs =
      stateObj && Array.isArray(stateObj.attributes.connectors)
        ? [
            ...new Set(
              stateObj.attributes.connectors.flatMap((c) =>
                Array.isArray(c.plug_types) ? c.plug_types : []
              )
            ),
          ]
        : [];
    const plugOptions = (sitePlugs.length ? sitePlugs : KNOWN_PLUG_TYPES).map(
      (value) => ({ value, label: shortPlug(value, lang) || value })
    );
    this._form.schema = [
      {
        name: "entity",
        required: true,
        selector: { entity: { domain: "sensor", integration: "swiss_charging_map" } },
      },
      { name: "title", selector: { text: {} } },
      {
        name: "plug_types",
        selector: {
          select: { multiple: true, mode: "dropdown", options: plugOptions },
        },
      },
      {
        name: "hidden_badges",
        selector: {
          select: { multiple: true, mode: "dropdown", options: [{ value: "availability", label: BADGE_LABELS.availability[lang] || BADGE_LABELS.availability.en }, { value: "accessibility", label: BADGE_LABELS.accessibility[lang] || BADGE_LABELS.accessibility.en }, { value: "renewable", label: BADGE_LABELS.renewable[lang] || BADGE_LABELS.renewable.en }] },
        },
      },
    ];
    this._form.computeLabel = (schema) =>
      (EDITOR_LABELS[schema.name] &&
        (EDITOR_LABELS[schema.name][lang] || EDITOR_LABELS[schema.name].en)) ||
      schema.name;
  }
}

customElements.define("swiss-charging-stations-card-editor", SwissChargingStationsCardEditor);

class SwissChargingStationsCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("swiss-charging-stations-card: 'entity' is required");
    }
    this._config = config;
  }

  static async getConfigElement() {
    // ha-form and the selector components are lazy-loaded by the frontend;
    // loading a core card editor first guarantees they are registered.
    if (window.loadCardHelpers) {
      const helpers = await window.loadCardHelpers();
      const entitiesCard = await helpers.createCardElement({ type: "entities", entities: [] });
      if (entitiesCard && entitiesCard.constructor.getConfigElement) {
        await entitiesCard.constructor.getConfigElement();
      }
    }
    return document.createElement("swiss-charging-stations-card-editor");
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig(hass) {
    const candidate = Object.keys(hass.states).find((id) =>
      id.startsWith("sensor.charging_station_favorite")
    );
    return { entity: candidate || "" };
  }

  _lang() {
    const lang = (this._hass && this._hass.language) || "en";
    return lang.split("-")[0];
  }

  _render() {
    if (!this._hass || !this._config) return;
    const stateObj = this._hass.states[this._config.entity];

    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
    }

    if (!stateObj) {
      this._root.innerHTML = `<ha-card><div style="padding:16px;">
        Entity not found: ${this._escape(this._config.entity)}</div></ha-card>`;
      return;
    }

    const attrs = stateObj.attributes;
    const isSite = Array.isArray(attrs.connectors);
    // Renewable-energy badge: shown when the operator declares green power —
    // for a site only when no connector explicitly says otherwise.
    // Accessibility badge: localized text from the sensor, color keyed off
    // the raw declaration (absent in sources without the field).
    const hiddenBadges = new Set(this._config.hidden_badges || []);
    const accText = attrs.accessibility_text;
    const accClass =
      attrs.accessibility === "Restricted access"
        ? "acc-restricted"
        : attrs.accessibility === "Paying publicly accessible"
          ? "acc-paying"
          : "acc-free";
    let renewable;
    if (isSite) {
      const flags = attrs.connectors.map((c) => c.renewable);
      renewable = flags.some((f) => f === true) && !flags.some((f) => f === false);
    } else {
      renewable = attrs.renewable_energy === true;
    }
    const title =
      this._config.title || attrs.friendly_name || this._config.entity;
    const addressParts = [
      attrs.street,
      [attrs.postal_code, attrs.city].filter(Boolean).join(" "),
    ].filter(Boolean);
    const address = addressParts.join(", ");
    // Localized server-built weekly schedule ("Mo–Fr 08:00–20:00 · Sa
    // 07:30–18:00" / "24 h geöffnet"), absent when the source has no
    // schedule data for this site.
    const openingHours = attrs.opening_hours || "";
    // Published ad-hoc price ("0.57 CHF/kWh"), absent for operators that
    // publish none — language-neutral source text, shown as-is.
    const price = attrs.price || "";

    // When the site is closed (outside opening hours) the operator may keep
    // reporting connectors as Available — technically correct, but you can't
    // charge right now, so the tiles must not stay green (user report).
    const siteClosed = attrs.site_status === "closed";
    const closedWord =
      SITE_STATUS_WORDS.closed[this._lang()] || SITE_STATUS_WORDS.closed.en;

    // Optional per-card plug-type filter (config `plug_types`, set in the
    // visual editor): purely visual — the favorite, its sensors, and the
    // dashboard row keep covering the whole site. Availability badge counts
    // only the visible connectors then. Tiles keep their original number so
    // they still match the per-connector sensors. If the filter matches
    // nothing (e.g. the operator renamed its plug strings), fall back to
    // showing everything rather than a dead card.
    const visiblePlugs =
      Array.isArray(this._config.plug_types) && this._config.plug_types.length
        ? this._config.plug_types
        : null;
    const plugMatch = (plugs) =>
      !visiblePlugs ||
      (Array.isArray(plugs) && plugs.some((p) => visiblePlugs.includes(p)));

    let boxes;
    let badge = "";
    let badgeClass = "";
    if (isSite) {
      let shown = attrs.connectors.map((c, i) => ({ c, num: i + 1 }));
      if (visiblePlugs) {
        const filtered = shown.filter(({ c }) => plugMatch(c.plug_types));
        if (filtered.length) shown = filtered;
      }
      const filtering = shown.length !== attrs.connectors.length;
      const total = filtering
        ? shown.length
        : attrs.count_total || attrs.connectors.length;
      const available = filtering
        ? shown.filter(({ c }) => c.status_raw === "Available").length
        : Number(stateObj.state) || 0;
      const siteWords = SITE_STATUS_WORDS[attrs.site_status];
      if (siteWords) {
        // Whole site closed / out of service — show the reason instead of
        // "0/6". Full-day closures (e.g. Sundays) say "closed today" so the
        // schedule-driven closure reads differently from being outside
        // today's hours.
        badge =
          siteClosed && attrs.closed_all_day_today
            ? CLOSED_TODAY_WORDS[this._lang()] || CLOSED_TODAY_WORDS.en
            : siteWords[this._lang()] || siteWords.en;
        badgeClass = siteClosed ? "closed" : "alert";
      } else {
        // Availability badge mirrors the tile colors: green while something
        // is still free, red when every connector is taken.
        const word = AVAILABLE_WORD[this._lang()] || AVAILABLE_WORD.en;
        badge = `${available}/${total} ${word}`;
        badgeClass = available > 0 ? "ok" : "busy";
      }
      boxes = shown.map(({ c, num }) =>
        this._box(
          siteClosed ? "Closed" : c.status_raw,
          siteClosed ? closedWord : c.status,
          c.power_kw,
          shortPlugs(c.plug_types, this._lang()),
          num
        )
      );
    } else {
      boxes = [
        this._box(
          siteClosed ? "Closed" : attrs.status_raw,
          siteClosed ? closedWord : stateObj.state,
          attrs.power_kw,
          shortPlugs(attrs.plug_types, this._lang()),
          null
        ),
      ];
    }

    this._root.innerHTML = `
      <style>
        .wrap { padding: 12px 16px 16px; }
        .head {
          display: flex; align-items: flex-start; justify-content: space-between;
          gap: 8px; margin-bottom: 2px;
        }
        .badges {
          flex: none; display: flex; flex-direction: column;
          gap: 4px; align-items: stretch; min-width: 84px;
        }
        .title {
          font-size: 1.15em; font-weight: 500;
          color: var(--primary-text-color);
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .badge {
          font-size: 0.85em; font-weight: 500; text-align: center;
          padding: 2px 10px; border-radius: 12px;
          background: var(--secondary-background-color, rgba(127,127,127,.15));
          color: var(--primary-text-color);
        }
        .badge.acc-free,
        .badge.acc-restricted,
        .badge.acc-paying {
          background: #546e7a;
          color: #fff;
        }
        .badge.eco {
          background: #1B5E20;
          padding: 3px 8px;
          display: flex; align-items: center; justify-content: center;
        }
        .badge.alert {
          background: var(--disabled-text-color, #757575);
          color: #fff;
        }
        .badge.closed {
          background: var(--info-color, #1565c0);
          color: #fff;
        }
        .badge.ok {
          background: var(--success-color, #2e7d32);
          color: #fff;
        }
        .badge.busy {
          background: var(--error-color, #c62828);
          color: #fff;
        }
        .addr {
          font-size: 0.85em; color: var(--secondary-text-color);
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .subhead { margin-bottom: 12px; }
        .grid {
          display: grid; gap: 8px;
          grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
        }
        .box {
          border-radius: 8px; padding: 10px 8px; color: #fff;
          display: flex; flex-direction: column; align-items: center;
          gap: 2px; text-align: center; cursor: pointer;
          min-height: 64px; justify-content: center;
        }
        .box .num { font-size: 1em; font-weight: 700; opacity: 0.95; }
        .box .plug { font-size: 0.95em; font-weight: 600; }
        .box .power { font-size: 1.1em; font-weight: 600; }
        .box .status { font-size: 0.85em; font-weight: 500; }
      </style>
      <ha-card>
        <div class="wrap">
          <div class="head">
            <div class="title">${this._escape(title)}</div>
            <div class="badges">
            ${badge && !hiddenBadges.has("availability") ? `<div class="badge${badgeClass ? ` ${badgeClass}` : ""}">${this._escape(badge)}</div>` : ""}
            ${accText && !hiddenBadges.has("accessibility") ? `<div class="badge ${accClass}">${this._escape(accText)}</div>` : ""}
            ${renewable && !hiddenBadges.has("renewable") ? `<div class="badge eco" title="Renewable energy"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="#fff" d="M17,8C8,10 5.9,16.17 3.82,21.34L5.71,22L6.66,19.7C7.14,19.87 7.64,20 8,20C19,20 22,3 22,3C21,5 14,5.25 9,6.25C4,7.25 2,11.5 2,13.5C2,15.5 3.75,17.25 3.75,17.25C7,8 17,8 17,8Z"/></svg></div>` : ""}
            </div>
          </div>
          <div class="subhead">
            ${address ? `<div class="addr">${this._escape(address)}</div>` : ""}
            ${openingHours ? `<div class="addr">${this._escape(openingHours)}</div>` : ""}
            ${price ? `<div class="addr">${this._escape(price)}</div>` : ""}
          </div>
          <div class="grid">${boxes.join("")}</div>
        </div>
      </ha-card>`;

    this._root.querySelector("ha-card").addEventListener("click", () => {
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          bubbles: true,
          composed: true,
          detail: { entityId: this._config.entity },
        })
      );
    });
  }

  _box(statusRaw, statusText, powerKw, plugShort, num) {
    const color = STATUS_COLORS[statusRaw] || UNKNOWN_COLOR;
    const power = powerKw ? `${Number(powerKw)} kW` : "";
    return `<div class="box" style="background:${color};">
      ${num !== null ? `<div class="num">#${num}</div>` : ""}
      ${plugShort ? `<div class="plug">${this._escape(plugShort)}</div>` : ""}
      ${power ? `<div class="power">${this._escape(power)}</div>` : ""}
      <div class="status">${this._escape(statusText || "?")}</div>
    </div>`;
  }

  _escape(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }
}

customElements.define("swiss-charging-stations-card", SwissChargingStationsCard);
// Backward-compatibility alias for cards created under the former element name.
customElements.define("ich-tanke-strom-card", class extends SwissChargingStationsCard {});

window.customCards = window.customCards || [];
window.customCards.push({
  type: "swiss-charging-stations-card",
  name: "Swiss Charging Stations Card",
  description:
    "Colored per-connector status boxes for a favorite charging station or site (ich-tanke-strom.ch).",
  preview: true,
});

/* ===================================================================== */
/* Everything below is the dashboard strategy — self-contained and kept   */
/* inside an IIFE so its names never collide with another integration     */
/* shipping the same core in the global scope.                            */
/* ===================================================================== */
(() => {
/* =====================================================================
 * Dashboard strategy core — shared building blocks
 * =====================================================================
 * A Lovelace dashboard strategy generates a dashboard in the browser at
 * render time. Nothing is written to .storage: the dashboard belongs to
 * the user, the integration only supplies the recipe.
 *
 * ⚠️ This block is duplicated into every integration that ships a
 * strategy. Each integration is its own HACS repository and must not
 * depend on another one being installed, so a shared file is not an
 * option. Keep the copies in sync and bump CORE_VERSION when the shared
 * part changes — it identifies which revision a copy was taken from.
 * ===================================================================== */

const CORE_VERSION = "1.1.1";

/* 1.1.1 - review follow-ups on the `strategy:` options
 *   (a) `map: false` only dropped the view with path "map". Where the map is
 *       a section inside another view (or a card in a panel view) it stayed
 *       visible. The option now also strips map cards out of every view: a
 *       section left with nothing but headings is dropped, and a view that
 *       ends up without any sections or cards is dropped as well.
 *   (b) The view flavour hardcoded max_columns: 2 and discarded the user's
 *       `max_columns`. It now uses the option when valid, else the value of
 *       the first sections view, else 2.
 *   (c) The view flavour copied only sections and cards, losing a view's
 *       `header` and `badges`. Both are carried over from the first view
 *       that has them. */

/* --- Registry access -------------------------------------------------
 * The registries are the only reliable way to find an integration's
 * entities: entity_id patterns are user-editable, unique_id is not.
 * Both calls are cheap and cached by the frontend for the render pass.
 */
async function loadRegistry(hass) {
  const [entities, devices] = await Promise.all([
    hass.callWS({ type: "config/entity_registry/list" }),
    hass.callWS({ type: "config/device_registry/list" }),
  ]);
  return { entities, devices };
}

/** All registry entries belonging to one integration (platform == domain). */
function entriesOfDomain(entities, domain) {
  return entities.filter((e) => e.platform === domain && !e.disabled_by);
}

/** Registry entries of one config entry, keyed by unique_id suffix.
 *  Mirrors the `f"{entry_id}_{suffix}"` convention the integrations use. */
function bySuffix(entities, configEntryId) {
  const out = {};
  const prefix = `${configEntryId}_`;
  for (const e of entities) {
    if (e.config_entry_id !== configEntryId) continue;
    if (typeof e.unique_id === "string" && e.unique_id.startsWith(prefix)) {
      out[e.unique_id.slice(prefix.length)] = e.entity_id;
    }
  }
  return out;
}

/** Group an integration's entities by the device they belong to.
 *  Returns [{device, entities:[registryEntry,...]}] sorted by device name. */
function groupByDevice(domainEntries, devices) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  const groups = new Map();
  for (const e of domainEntries) {
    if (!e.device_id) continue;
    if (!groups.has(e.device_id)) groups.set(e.device_id, []);
    groups.get(e.device_id).push(e);
  }
  return [...groups.entries()]
    .map(([id, list]) => ({ device: byId.get(id), entities: list }))
    .filter((g) => g.device)
    .sort((a, b) => deviceName(a.device).localeCompare(deviceName(b.device)));
}

function deviceName(device) {
  return device.name_by_user || device.name || "";
}

/* --- Card helpers ---------------------------------------------------- */

const heading = (text, icon, badges) => {
  const card = { type: "heading", heading: text };
  if (icon) card.icon = icon;
  if (badges && badges.length) card.badges = badges;
  return card;
};

const grid = (cards, columnSpan) => {
  const section = { type: "grid", cards: cards.filter(Boolean) };
  if (columnSpan) section.column_span = columnSpan;
  return section;
};

const tile = (entity, extra = {}) => ({ type: "tile", entity, ...extra });

/** Map card fed from the integration's geo_location source.
 *  Deliberately uses geo_location_sources instead of an entity list: the
 *  markers are hidden entities, and the source keeps working when the
 *  set of markers changes between renders.
 *  labelAttribute writes the marker label into the source object, which is
 *  where the map card reads a geo-location source's label config from — the
 *  card-level label_mode only applies to `entities`. */
const mapCard = (domain, opts = {}) => ({
  type: "map",
  geo_location_sources: [
    opts.labelAttribute
      ? { source: domain, label_mode: "attribute", attribute: opts.labelAttribute }
      : domain,
  ],
  entities: opts.entities || ["zone.home"],
  default_zoom: opts.zoom ?? 8,
  theme_mode: "auto",
  grid_options: { columns: 12, rows: opts.rows ?? 6 },
});

/** Shown instead of an empty dashboard — an empty dashboard looks broken
 *  and gives the user nothing to act on. */
const emptyNotice = (text) => ({
  type: "markdown",
  content: text,
});

/* --- Localisation ----------------------------------------------------
 * Strategies run in the frontend, so hass.language is authoritative.
 * Falls back to English for any language the integration does not ship.
 */
function translator(strings, hass) {
  const lang = (hass.language || "en").split("-")[0];
  const table = strings[lang] || strings.en;
  return (key) => (table && table[key]) || (strings.en && strings.en[key]) || key;
}

/* --- Strategy base ---------------------------------------------------
 * Wraps the parts every strategy repeats: load registries, bail out
 * gracefully when the integration is not set up, and hand the concrete
 * strategy a prepared context.
 */

/* Options a user may put under `strategy:` in the raw configuration editor.
 * They are handled here in the core, so every integration supports the same
 * set without shipping its own option code:
 *
 *   map: false        drop the map: the full-screen map view as well as the
 *                     map cards inside section and panel views
 *   title: "..."      override the title
 *   max_columns: 3    column count of the generated section views (the view
 *                     flavour honours it too)
 *
 * Unknown keys are ignored on purpose - a strategy config is free-form, and a
 * typo should not take the dashboard down. */
const validColumns = (value) => {
  const cols = Number(value);
  return Number.isFinite(cols) && cols > 0 ? cols : undefined;
};

const isMapCard = (card) => Boolean(card) && card.type === "map";
const isHeadingCard = (card) => Boolean(card) && card.type === "heading";

/* Remove the map cards of one view. A section is dropped once only headings
 * remain - a heading merely labels the map that was just removed. Returns
 * null when nothing is left to show; views without a map card come back
 * untouched. */
const withoutMapCards = (view) => {
  let touched = false;
  const out = { ...view };
  if (Array.isArray(view.sections)) {
    out.sections = [];
    for (const section of view.sections) {
      const cards = Array.isArray(section.cards) ? section.cards : [];
      if (!cards.some(isMapCard)) {
        out.sections.push(section);
        continue;
      }
      touched = true;
      const rest = cards.filter((c) => !isMapCard(c));
      if (rest.some((c) => !isHeadingCard(c))) out.sections.push({ ...section, cards: rest });
    }
  }
  if (Array.isArray(view.cards) && view.cards.some(isMapCard)) {
    touched = true;
    out.cards = view.cards.filter((c) => !isMapCard(c));
  }
  if (!touched) return view;
  const empty = !(out.sections && out.sections.length) && !(out.cards && out.cards.length);
  return empty ? null : out;
};

const applyViewOptions = (views, config) => {
  const cfg = config || {};
  let out = views;
  if (cfg.map === false) {
    out = out
      .filter((v) => v.path !== "map")
      .map(withoutMapCards)
      .filter(Boolean);
  }
  const cols = validColumns(cfg.max_columns);
  if (cols) {
    out = out.map((v) => (v.type === "sections" ? { ...v, max_columns: cols } : v));
  }
  return out;
};

/* A view strategy must return exactly ONE view, while build() yields a list.
 * Section views are merged by concatenating their sections. A panel view (the
 * map) has no sections, so its cards become one full-width section instead -
 * that keeps the map visible rather than silently dropping it. */
const flattenToView = (views, title, icon, config) => {
  const sections = [];
  for (const v of views) {
    if (Array.isArray(v.sections) && v.sections.length) {
      sections.push(...v.sections);
    } else if (Array.isArray(v.cards) && v.cards.length) {
      sections.push(
        grid(
          v.cards.map((c) => ({
            ...c,
            grid_options: { columns: "full", rows: (c.grid_options || {}).rows ?? 8 },
          }))
        )
      );
    }
  }
  const sized = views.find((v) => v.type === "sections" && validColumns(v.max_columns));
  const view = {
    title,
    icon,
    type: "sections",
    max_columns: validColumns((config || {}).max_columns) ?? (sized ? validColumns(sized.max_columns) : 2),
    sections,
  };
  // header and badges live outside the sections and would be lost by the
  // merge above - keep the first ones the build produced.
  const withHeader = views.find((v) => v.header);
  if (withHeader) view.header = withHeader.header;
  const withBadges = views.find((v) => Array.isArray(v.badges) && v.badges.length);
  if (withBadges) view.badges = withBadges.badges;
  return view;
};

function defineDashboardStrategy(name, { domain, title, icon, build, strings, description }) {
  /* Shared by both strategy flavours: everything up to the finished view list. */
  const buildViews = async (config, hass) => {
    const t = translator(strings || {}, hass);
    let registry;
    try {
      registry = await loadRegistry(hass);
    } catch (err) {
      // Registry unreachable: render a readable message rather than
      // letting the dashboard fail with a blank screen.
      return [{ title: title, cards: [emptyNotice(`\u26a0\ufe0f ${err}`)] }];
    }
    const domainEntries = entriesOfDomain(registry.entities, domain);
    if (!domainEntries.length) {
      return [{ title: title, icon, cards: [emptyNotice(t("not_configured"))] }];
    }
    const views = await build({
      hass,
      config,
      t,
      domain,
      entities: domainEntries,
      devices: registry.devices,
      allEntities: registry.entities,
      helpers: { heading, grid, tile, mapCard, emptyNotice, bySuffix, groupByDevice, deviceName },
    });
    return applyViewOptions(views, config);
  };

  class Strategy extends HTMLElement {
    static async generate(config, hass) {
      const views = await buildViews(config, hass);
      return { title: (config && config.title) || title, views };
    }
  }

  /* The view flavour: fills a single view of a dashboard the user built
   * themselves, so adjusting the layout no longer requires "take control". */
  class ViewStrategy extends HTMLElement {
    static async generate(config, hass) {
      const views = await buildViews(config, hass);
      return flattenToView(views, (config && config.title) || title, icon, config);
    }
  }

  // getCreateSuggestions lets Home Assistant offer sensible defaults when the
  // strategy is picked from the "new dashboard" dialog.
  Strategy.getCreateSuggestions = () => ({ title, icon });

  customElements.define(`ll-strategy-dashboard-${name}`, Strategy);
  customElements.define(`ll-strategy-view-${name}`, ViewStrategy);

  // Announce the strategy to the frontend so it appears in the dashboard
  // creation dialog instead of having to be typed into the raw editor.
  window.customStrategies = window.customStrategies || [];
  if (!window.customStrategies.some((s) => s.type === name)) {
    window.customStrategies.push({
      type: name,
      strategyType: "dashboard",
      name: title,
      description: description || "",
    });
  }
  return Strategy;
}


/* =====================================================================
 * Dashboard strategy: Swiss Charging Stations
 * =====================================================================
 * Generates the dashboard in the browser at render time. Earlier versions
 * created a dashboard in the user's Lovelace storage and kept a card per
 * favorite in sync with it; a strategy produces the same layout without
 * writing anything into the user's configuration.
 *
 * It also keeps itself current: adding or removing a favorite changes the
 * dashboard on the next load, with no card to sync and no leftovers when a
 * favorite is deleted.
 *
 * Usage — create an empty dashboard, open the raw configuration editor and
 * replace its content with:
 *
 *     strategy:
 *       type: custom:swiss-charging-stations
 *     views: []
 * ===================================================================== */

const SCS_STRINGS = {
  en: {
    stations: "Charging stations",
    map: "Map",
    not_configured:
      "### Swiss Charging Stations is not set up yet\n\nAdd the integration under **Settings → Devices & services** first. This dashboard then fills itself — there is nothing to configure here.",
  },
  de: {
    stations: "Ladestationen",
    map: "Karte",
    not_configured:
      "### Swiss Charging Stations ist noch nicht eingerichtet\n\nFüge die Integration zuerst unter **Einstellungen → Geräte & Dienste** hinzu. Dieses Dashboard füllt sich danach von selbst — hier ist nichts einzustellen.",
  },
  fr: {
    stations: "Bornes de recharge",
    map: "Carte",
    not_configured:
      "### Swiss Charging Stations n'est pas encore configuré\n\nAjoutez d'abord l'intégration sous **Paramètres → Appareils et services**. Ce tableau de bord se remplit ensuite tout seul.",
  },
  it: {
    stations: "Stazioni di ricarica",
    map: "Mappa",
    not_configured:
      "### Swiss Charging Stations non è ancora configurato\n\nAggiungi prima l'integrazione in **Impostazioni → Dispositivi e servizi**. Questa dashboard si riempie poi da sola.",
  },
};

/* unique_id suffixes carrying a favorite's headline values. Everything else
 * a favorite produces is per-connector detail, which the bundled card below
 * already renders as status boxes — repeating it as tiles would bury the
 * summary. Mirrors the unique_id scheme of the sensor platform. */
const SCS_SUMMARY_SUFFIXES = new Set([
  "free",
  "available",
  "status",
  "site_status",
  "price",
  "power",
  "plug_type",
  "operator",
  "station_id",
]);

const SCS_isSummary = (suffix) =>
  SCS_SUMMARY_SUFFIXES.has(suffix) ||
  suffix.startsWith("free_") ||
  suffix.startsWith("available_");

defineDashboardStrategy("swiss-charging-stations", {
  domain: "swiss_charging_map",
  title: "Swiss Charging Stations",
  icon: "mdi:ev-station",
  description: "Map of every charging station in range plus one section per favorite, generated live from the integration.",
  strings: SCS_STRINGS,

  async build({ t, domain, entities, devices, allEntities, helpers }) {
    const { heading, grid, tile, mapCard, groupByDevice, deviceName, bySuffix } = helpers;
    const views = [];

    // --- Map ----------------------------------------------------------
    // The markers come from the radius entry; a setup with favorites only
    // has none, and an empty map would just look broken.
    const hasMarkers = entities.some((e) => e.entity_id.startsWith("geo_location."));
    if (hasMarkers) {
      views.push({
        title: t("map"),
        path: "map",
        icon: "mdi:map-marker-radius",
        type: "panel",
        cards: [mapCard(domain, { zoom: 11, rows: 12, labelAttribute: "status" })],
      });
    }

    // --- One section per config entry ---------------------------------
    // Each entry (the radius search and every favorite) is its own device,
    // so grouping by device gives exactly one section per entry.
    // The radius search goes first — it is the entry point, and its filter
    // entities are what a user reaches for. Favorites follow, alphabetically
    // as groupByDevice already returns them.
    const sections = [];
    const searchSections = [];
    for (const group of groupByDevice(entities, devices)) {
      const name = deviceName(group.device);
      const entryId = group.entities.find((e) => e.config_entry_id)?.config_entry_id;
      const ids = entryId ? bySuffix(allEntities, entryId) : {};

      // A favorite is driven by its status (single charge point) or its
      // available count (whole site). The radius entry carries the same two
      // suffixes as *filter* entities (select/number), which the bundled
      // card cannot render — hence the explicit sensor check.
      const cardEntity = [ids.status, ids.available].find(
        (entityId) => typeof entityId === "string" && entityId.startsWith("sensor.")
      );

      const cards = [heading(name, "mdi:ev-station")];
      if (cardEntity) {
        cards.push({ type: "custom:swiss-charging-stations-card", entity: cardEntity, title: name });
      }

      // Alongside the card only the headline values; without a card (the
      // radius entry) everything the entry offers, filters included.
      const summaryIds = new Set(
        Object.entries(ids)
          .filter(([suffix]) => SCS_isSummary(suffix))
          .map(([, entityId]) => entityId)
      );
      cards.push(
        ...group.entities
          .filter(
            (e) =>
              !e.hidden_by &&
              !e.entity_id.startsWith("geo_location.") &&
              e.entity_id !== cardEntity &&
              (cardEntity ? summaryIds.has(e.entity_id) : true)
          )
          .map((e) => e.entity_id)
          // Registry order is not stable — sort so the layout does not
          // reshuffle between reloads.
          .sort()
          .map((entityId) => tile(entityId, { grid_options: { columns: 6 } }))
      );

      (cardEntity ? sections : searchSections).push(grid(cards));
    }
    sections.unshift(...searchSections);

    if (sections.length) {
      views.push({
        title: t("stations"),
        path: "stations",
        icon: "mdi:star",
        type: "sections",
        max_columns: 2,
        sections,
      });
    }

    return views;
  },
});
})();
