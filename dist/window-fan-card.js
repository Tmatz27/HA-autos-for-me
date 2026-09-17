/**
 * Window Fan Card
 *
 * A Lovelace card for IR-remote window fans that report no state of their
 * own. It decodes the fan's real mode + speed from a smart plug's power
 * draw, shows them as indicator lights, and drives the fan by working out
 * exactly how many times to press the remote's mode/speed toggle buttons.
 *
 * No helpers, template sensors or scripts are required for the card itself.
 */

const CARD_VERSION = "1.0.0";

const MODES = ["cool", "exhaust", "circulate"];
const SPEEDS = ["low", "med", "high"];

const DEFAULT_WATTS = {
  off_below: 10,
  exhaust_low: 31,
  exhaust_med: 33,
  exhaust_high: 36,
  cool_low: 45,
  cool_med: 48,
  cool_high: 51,
};

const MODE_META = {
  cool: {
    label: "Cool",
    color: "#3b82f6",
    path: "M11,3H13V7.68L16.29,4.38L17.71,5.79L14,9.5H18V6L21,9L18,12H14L17.71,15.71L16.29,17.13L13,13.83V18H11V13.83L7.71,17.13L6.29,15.71L10,12H6V9L3,12L6,15V9H10L6.29,5.79L7.71,4.38L11,7.68V3Z",
  },
  exhaust: {
    label: "Exhaust",
    color: "#f97316",
    path: "M12,11A1,1 0 0,0 11,12A1,1 0 0,0 12,13A1,1 0 0,0 13,12A1,1 0 0,0 12,11M12.5,2C17,2 17.11,5.57 14.75,6.75C13.76,7.24 13.32,8.29 13.13,9.22C13.61,9.42 14.03,9.73 14.35,10.13C18.05,8.13 22,8.92 22,12.5C22,17 18.43,17.11 17.25,14.75C16.76,13.76 15.71,13.32 14.78,13.13C14.58,13.61 14.27,14.03 13.87,14.35C15.87,18.05 15.08,22 11.5,22C7,22 6.89,18.43 9.25,17.25C10.24,16.76 10.68,15.71 10.87,14.78C10.39,14.58 9.97,14.27 9.65,13.87C5.95,15.87 2,15.08 2,11.5C2,7 5.57,6.89 6.75,9.25C7.24,10.24 8.29,10.68 9.22,10.87C9.42,10.39 9.73,9.97 10.13,9.65C8.13,5.95 8.92,2 12.5,2Z",
  },
  circulate: {
    label: "Circulate",
    color: "#a855f7",
    path: "M12,18A6,6 0 0,1 6,12C6,11 6.25,10.03 6.7,9.2L5.24,7.74C4.46,8.97 4,10.43 4,12A8,8 0 0,0 12,20V23L16,19L12,15V18M12,4V1L8,5L12,9V6A6,6 0 0,1 18,12C18,13 17.75,13.97 17.3,14.8L18.76,16.26C19.54,15.03 20,13.57 20,12A8,8 0 0,0 12,4Z",
  },
};

const SPEED_META = {
  low: { label: "Low", color: "#22c55e", bars: 1 },
  med: { label: "Med", color: "#f59e0b", bars: 2 },
  high: { label: "High", color: "#ef4444", bars: 3 },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Builds the full 9-entry wattage lookup table. Circulate runs one fan in
 * each direction, so its draw is the average of cool and exhaust at the
 * same speed - no need to measure it separately. */
function buildWattTable(w) {
  const table = [];
  for (const speed of SPEEDS) {
    const cool = Number(w[`cool_${speed}`]);
    const exhaust = Number(w[`exhaust_${speed}`]);
    table.push({ mode: "cool", speed, watts: cool });
    table.push({ mode: "exhaust", speed, watts: exhaust });
    table.push({ mode: "circulate", speed, watts: (cool + exhaust) / 2 });
  }
  return table;
}

function decodeWatts(watts, w) {
  if (!Number.isFinite(watts) || watts < Number(w.off_below)) {
    return { on: false, mode: null, speed: null };
  }
  let best = null;
  let bestDistance = Infinity;
  for (const row of buildWattTable(w)) {
    const distance = Math.abs(row.watts - watts);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = row;
    }
  }
  return { on: true, mode: best.mode, speed: best.speed };
}

function speedBarsSvg(bars, color, dim) {
  const heights = [7, 11, 15];
  const rects = heights
    .map((h, i) => {
      const filled = i < bars;
      const fill = filled ? color : "currentColor";
      const opacity = filled ? 1 : 0.35;
      return `<rect x="${4 + i * 6}" y="${19 - h}" width="4" height="${h}" rx="1" fill="${fill}" opacity="${opacity}"/>`;
    })
    .join("");
  return `<svg viewBox="0 0 24 24" width="24" height="24" style="color:${dim}">${rects}</svg>`;
}

function iconSvg(path, color, size = 24) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}"><path fill="${color}" d="${path}"/></svg>`;
}

class WindowFanCard extends HTMLElement {
  constructor() {
    super();
    this._busy = false;
    this._root = null;
  }

  static getConfigElement() {
    return document.createElement("window-fan-card-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:window-fan-card",
      name: "Window Fan",
      ir_device: "",
      mode_command: "mode_toggle",
      speed_command: "speed_toggle",
      press_delay: 2,
    };
  }

  setConfig(config) {
    if (!config.power_sensor) {
      throw new Error("window-fan-card: 'power_sensor' is required");
    }
    if (!config.remote) {
      throw new Error("window-fan-card: 'remote' is required");
    }
    if (!config.ir_device) {
      throw new Error("window-fan-card: 'ir_device' is required");
    }
    this._config = {
      name: "Window Fan",
      mode_command: "mode_toggle",
      speed_command: "speed_toggle",
      press_delay: 2,
      boot_delay: 4,
      ...config,
      watts: { ...DEFAULT_WATTS, ...(config.watts || {}) },
    };
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  _state() {
    const raw = this._hass?.states[this._config.power_sensor]?.state;
    return decodeWatts(parseFloat(raw), this._config.watts);
  }

  _build() {
    this.innerHTML = `
      <ha-card>
        <style>
          .wfc { padding: 16px; }
          .wfc-header { display:flex; align-items:center; gap:14px; margin-bottom:4px; }
          .wfc-title { font-size:18px; font-weight:600; line-height:1.2; }
          .wfc-sub { font-size:14px; color: var(--secondary-text-color); margin-top:2px; }
          .wfc-row { display:flex; justify-content:space-around; margin-top:14px; }
          .wfc-light { display:flex; flex-direction:column; align-items:center; gap:6px;
                       cursor:pointer; user-select:none; }
          .wfc-dot { width:62px; height:62px; border-radius:50%; display:flex;
                     align-items:center; justify-content:center;
                     transition: background .18s ease, box-shadow .18s ease; }
          .wfc-dot.sm { width:54px; height:54px; }
          .wfc-label { font-size:12px; color: var(--secondary-text-color); }
          .wfc-label.on { color: var(--primary-text-color); font-weight:600; }
          .wfc-divider { height:1px; background: var(--divider-color); margin:16px 0 12px; }
          .wfc-pills { display:flex; gap:10px; }
          .wfc-pill { flex:1; display:flex; align-items:center; gap:9px; padding:8px 12px;
                      border-radius:14px; background: rgba(127,127,127,.08); cursor:pointer; }
          .wfc-pill-label { font-size:11px; color: var(--secondary-text-color); line-height:1.3; }
          .wfc-pill-value { font-size:13px; font-weight:600; }
          .wfc-stats { display:flex; justify-content:space-around; margin-top:12px; }
          .wfc-stat { display:flex; align-items:center; gap:8px; }
          .wfc-stat-value { font-size:13px; font-weight:600; }
          .wfc-stat-label { font-size:11px; color: var(--secondary-text-color); }
          .wfc.busy { opacity:.55; pointer-events:none; }
          .wfc-busy-note { text-align:center; font-size:12px; color: var(--secondary-text-color);
                           margin-top:10px; }
        </style>
        <div class="wfc"></div>
      </ha-card>
    `;
    this._root = this.querySelector(".wfc");
    this._root.addEventListener("click", (ev) => {
      const el = ev.target.closest("[data-action]");
      if (!el) return;
      const { action, value } = el.dataset;
      if (action === "mode") this._setState(value, null);
      else if (action === "speed") this._setState(null, value);
      else if (action === "power") this._togglePower();
      else if (action === "override") this._toggleOverride();
    });
    this._built = true;
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._built) this._build();

    const cfg = this._config;
    const st = this._state();
    const dim = "var(--disabled-text-color, #8a8a8a)";

    const headerColor = st.on ? MODE_META[st.mode].color : dim;
    const headerText = st.on
      ? `${MODE_META[st.mode].label} • ${SPEED_META[st.speed].label}`
      : "Off";

    const modeLights = MODES.map((mode) => {
      const meta = MODE_META[mode];
      const active = st.on && st.mode === mode;
      const bg = active ? `${meta.color}38` : "rgba(127,127,127,.08)";
      const glow = active ? `box-shadow:0 0 14px 3px ${meta.color}a6;` : "";
      return `
        <div class="wfc-light" data-action="mode" data-value="${mode}">
          <div class="wfc-dot" style="background:${bg};${glow}">
            ${iconSvg(meta.path, active ? meta.color : dim, 26)}
          </div>
          <div class="wfc-label${active ? " on" : ""}">${meta.label}</div>
        </div>`;
    }).join("");

    const speedLights = SPEEDS.map((speed) => {
      const meta = SPEED_META[speed];
      const active = st.on && st.speed === speed;
      const bg = active ? `${meta.color}38` : "rgba(127,127,127,.08)";
      const glow = active ? `box-shadow:0 0 12px 2px ${meta.color}a6;` : "";
      return `
        <div class="wfc-light" data-action="speed" data-value="${speed}">
          <div class="wfc-dot sm" style="background:${bg};${glow}">
            ${speedBarsSvg(meta.bars, active ? meta.color : dim, dim)}
          </div>
          <div class="wfc-label${active ? " on" : ""}">${meta.label}</div>
        </div>`;
    }).join("");

    const pills = [];
    if (cfg.power_switch) {
      const on = this._hass.states[cfg.power_switch]?.state === "on";
      const color = on ? "#22c55e" : dim;
      pills.push(`
        <div class="wfc-pill" data-action="power">
          ${iconSvg("M13,3H11V13H13V3M17.83,5.17L16.41,6.59C18.05,7.91 19,9.9 19,12A7,7 0 0,1 12,19A7,7 0 0,1 5,12C5,9.9 6.05,7.91 7.6,6.58L6.19,5.17C4.24,6.82 3,9.26 3,12A9,9 0 0,0 12,21A9,9 0 0,0 21,12C21,9.26 19.76,6.82 17.83,5.17Z", color, 20)}
          <div>
            <div class="wfc-pill-label">Power</div>
            <div class="wfc-pill-value" style="color:${color}">${on ? "On" : "Off"}</div>
          </div>
        </div>`);
    }
    if (cfg.override_boolean) {
      const on = this._hass.states[cfg.override_boolean]?.state === "on";
      const color = on ? "#f59e0b" : dim;
      pills.push(`
        <div class="wfc-pill" data-action="override">
          ${iconSvg("M9,11.24V7.5C9,6.12 10.12,5 11.5,5C12.88,5 14,6.12 14,7.5V11.24C15.24,12.13 16,13.53 16,15.13V16H7V15.13C7,13.53 7.76,12.13 9,11.24M11.5,3C9.01,3 7,5.01 7,7.5V9.5H6.5A2.5,2.5 0 0,0 4,12V13H19V12A2.5,2.5 0 0,0 16.5,9.5H16V7.5C16,5.01 13.99,3 11.5,3Z", color, 20)}
          <div>
            <div class="wfc-pill-label">Manual override</div>
            <div class="wfc-pill-value" style="color:${on ? color : "inherit"}">${on ? "Paused" : "Auto"}</div>
          </div>
        </div>`);
    }

    const stats = [];
    if (cfg.temperature_sensor) {
      const s = this._hass.states[cfg.temperature_sensor];
      stats.push(this._statHtml(
        "M15,13V5A3,3 0 0,0 12,2A3,3 0 0,0 9,5V13A5,5 0 1,0 15,13Z",
        "#f59e0b",
        s ? `${s.state} ${s.attributes.unit_of_measurement || ""}`.trim() : "-",
        "Room temp"
      ));
    }
    if (cfg.humidity_sensor) {
      const s = this._hass.states[cfg.humidity_sensor];
      stats.push(this._statHtml(
        "M12,20A6,6 0 0,1 6,14C6,10 12,3.25 12,3.25C12,3.25 18,10 18,14A6,6 0 0,1 12,20Z",
        "#38bdf8",
        s ? `${s.state}${s.attributes.unit_of_measurement || ""}` : "-",
        "Room humidity"
      ));
    }

    this._root.className = `wfc${this._busy ? " busy" : ""}`;
    this._root.innerHTML = `
      <div class="wfc-header">
        ${iconSvg(MODE_META.exhaust.path, headerColor, 42)}
        <div>
          <div class="wfc-title">${cfg.name}</div>
          <div class="wfc-sub">${headerText}</div>
        </div>
      </div>
      <div class="wfc-row">${modeLights}</div>
      <div class="wfc-row">${speedLights}</div>
      ${pills.length ? `<div class="wfc-divider"></div><div class="wfc-pills">${pills.join("")}</div>` : ""}
      ${stats.length ? `<div class="wfc-stats">${stats.join("")}</div>` : ""}
      ${this._busy ? `<div class="wfc-busy-note">Sending commands…</div>` : ""}
    `;
  }

  _statHtml(path, color, value, label) {
    return `
      <div class="wfc-stat">
        ${iconSvg(path, color, 18)}
        <div>
          <div class="wfc-stat-value">${value}</div>
          <div class="wfc-stat-label">${label}</div>
        </div>
      </div>`;
  }

  /** Presses the remote the exact number of times needed to reach the
   * target. Passing null for either axis leaves it where it is. */
  async _setState(targetMode, targetSpeed) {
    const cfg = this._config;
    this._busy = true;
    this._render();
    try {
      let current = this._state();

      if (!current.on) {
        if (cfg.power_switch) {
          await this._hass.callService("switch", "turn_on", {
            entity_id: cfg.power_switch,
          });
          await sleep(cfg.boot_delay * 1000);
        }
        const reread = this._state();
        // The fan always boots to cool/low; fall back to that if the power
        // sensor hasn't caught up yet.
        current = reread.on ? reread : { on: true, mode: "cool", speed: "low" };
      }

      const mode = targetMode || current.mode;
      const speed = targetSpeed || current.speed;
      const modePresses = (MODES.indexOf(mode) - MODES.indexOf(current.mode) + 3) % 3;
      const speedPresses = (SPEEDS.indexOf(speed) - SPEEDS.indexOf(current.speed) + 3) % 3;

      await this._press(cfg.mode_command, modePresses);
      await this._press(cfg.speed_command, speedPresses);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _press(command, times) {
    for (let i = 0; i < times; i++) {
      await this._hass.callService("remote", "send_command", {
        entity_id: this._config.remote,
        device: this._config.ir_device,
        command,
      });
      await sleep(this._config.press_delay * 1000);
    }
  }

  _togglePower() {
    this._hass.callService("switch", "toggle", {
      entity_id: this._config.power_switch,
    });
  }

  _toggleOverride() {
    this._hass.callService("input_boolean", "toggle", {
      entity_id: this._config.override_boolean,
    });
  }
}

const EDITOR_SCHEMA = [
  { name: "name", selector: { text: {} } },
  { name: "power_sensor", selector: { entity: { domain: "sensor" } } },
  { name: "power_switch", selector: { entity: { domain: "switch" } } },
  { name: "remote", selector: { entity: { domain: "remote" } } },
  { name: "ir_device", selector: { text: {} } },
  { name: "mode_command", selector: { text: {} } },
  { name: "speed_command", selector: { text: {} } },
  {
    name: "press_delay",
    selector: { number: { min: 0.5, max: 10, step: 0.5, mode: "box" } },
  },
  { name: "temperature_sensor", selector: { entity: { domain: "sensor" } } },
  { name: "humidity_sensor", selector: { entity: { domain: "sensor" } } },
  { name: "override_boolean", selector: { entity: { domain: "input_boolean" } } },
  {
    name: "watts",
    type: "expandable",
    schema: Object.keys(DEFAULT_WATTS).map((key) => ({
      name: key,
      selector: { number: { min: 0, max: 500, step: 0.1, mode: "box" } },
    })),
  },
];

const EDITOR_LABELS = {
  name: "Card name",
  power_sensor: "Smart plug power sensor (W)",
  power_switch: "Smart plug switch (for power on/off)",
  remote: "IR remote entity",
  ir_device: 'IR device name (as learned, e.g. "Window Fan")',
  mode_command: "Mode/function toggle command",
  speed_command: "Speed toggle command",
  press_delay: "Seconds between button presses",
  temperature_sensor: "Room temperature sensor (optional)",
  humidity_sensor: "Room humidity sensor (optional)",
  override_boolean: "Manual override helper (optional)",
  watts: "Measured wattages",
  off_below: "Off below (W)",
  exhaust_low: "Exhaust low (W)",
  exhaust_med: "Exhaust med (W)",
  exhaust_high: "Exhaust high (W)",
  cool_low: "Cool low (W)",
  cool_med: "Cool med (W)",
  cool_high: "Cool high (W)",
};

class WindowFanCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { watts: { ...DEFAULT_WATTS }, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _render() {
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = EDITOR_SCHEMA;
      this._form.computeLabel = (s) => EDITOR_LABELS[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: ev.detail.value },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.appendChild(this._form);
    }
    if (this._hass) this._form.hass = this._hass;
    this._form.data = this._config;
  }
}

customElements.define("window-fan-card", WindowFanCard);
customElements.define("window-fan-card-editor", WindowFanCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "window-fan-card",
  name: "Window Fan Card",
  description:
    "Mode/speed indicator lights and controls for an IR window fan, with state decoded from smart plug wattage.",
  preview: true,
  documentationURL: "https://github.com/Tmatz27/HA-autos-for-me",
});

console.info(
  `%c WINDOW-FAN-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#3b82f6;font-weight:700",
  "color:#3b82f6;background:#222"
);

