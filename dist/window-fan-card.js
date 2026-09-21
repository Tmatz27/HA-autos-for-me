/**
 * Window Fan Card
 *
 * A Lovelace card for IR-remote window fans that report no state of their
 * own. It decodes the fan's real mode + speed from a smart plug's power
 * draw, shows them as indicator lights, and drives the fan by working out
 * exactly how many times to press the remote's mode/speed toggle buttons.
 *
 * Standalone mode needs no helpers. Managed mode shares package state and commands.
 */

const CARD_VERSION = "1.2.2";

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
  circulate_low: null,
  circulate_med: null,
  circulate_high: null,
  max_deviation: 1,
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
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const RANGE_KEYS = ["off_below", "exhaust_low_upper", "exhaust_med_upper", "exhaust_high_upper", "circulate_low_upper", "circulate_med_upper", "circulate_high_upper", "cool_low_upper", "cool_med_upper"];

/** All nine states must be measured; motor direction does not establish watts. */
function buildWattTable(w) {
  const table = [];
  for (const speed of SPEEDS) {
    const cool = Number(w[`cool_${speed}`]);
    const exhaust = Number(w[`exhaust_${speed}`]);
    table.push({ mode: "cool", speed, watts: cool });
    table.push({ mode: "exhaust", speed, watts: exhaust });
    table.push({ mode: "circulate", speed, watts: Number(w[`circulate_${speed}`]) });
  }
  return table;
}

function decodeWatts(watts, w) {
  const unknown = (reason) => ({ on: null, mode: null, speed: null, reason });
  if ([w.off_below, w.max_deviation].some(v => v === null || v === "" || !Number.isFinite(Number(v)) || Number(v) < 0)) {
    return unknown("Configure valid off and maximum-difference wattages");
  }
  if (!Number.isFinite(watts) || watts < 0) return unknown("Power reading unavailable");
  if (watts < Number(w.off_below)) {
    return { on: false, mode: null, speed: null };
  }
  if (MODES.some(mode => SPEEDS.some(speed => {
    const v = w[`${mode}_${speed}`];
    return v === null || v === "" || !Number.isFinite(Number(v)) || Number(v) < Number(w.off_below);
  }))) return unknown("Calibration incomplete");
  let best = null;
  let bestDistance = Infinity;
  let tied = false;
  for (const row of buildWattTable(w)) {
    const distance = Math.abs(row.watts - watts);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = row;
      tied = false;
    } else if (Math.abs(distance - bestDistance) < 1e-9) {
      tied = true;
    }
  }
  if (tied || bestDistance > Number(w.max_deviation)) return unknown("Power reading does not identify a unique calibrated state");
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

  static getStubConfig(hass) {
    const fans = discoverFans(hass);
    return { type: "custom:window-fan-card", name: "Window Fan", setup_mode: "package",
      ...(fans.length === 1 ? { fan_package: fans[0].state_sensor } : {}) };
  }

  setConfig(config) {
    this._sourceConfig = { ...config };
    this._resolveConfig();
    this._built = false;
  }

  _resolveConfig() {
    this._config = { name: "Window Fan", mode_command: "mode_toggle", speed_command: "speed_toggle",
      press_delay: 2, boot_delay: 4, feedback_timeout: 20,
      ...resolveConfig(this._sourceConfig, this._hass),
      watts: { ...DEFAULT_WATTS, ...(this._sourceConfig.watts || {}) } };
  }

  set hass(hass) {
    this._hass = hass;
    if (this._sourceConfig) this._resolveConfig();
    this._render();
  }

  getCardSize() {
    return 5;
  }

  _state() {
    if (this._config.state_sensor) {
      const value = this._hass?.states[this._config.state_sensor]?.state;
      if (value === "off") return { on: false, mode: null, speed: null };
      const [mode, speed] = (value || "").split("_");
      if (MODES.includes(mode) && SPEEDS.includes(speed)) return { on: true, mode, speed };
      return { on: null, mode: null, speed: null, reason: "Waiting for valid shared fan state" };
    }
    const raw = this._hass?.states[this._config.power_sensor]?.state;
    return decodeWatts(raw == null || raw === "" ? NaN : Number(raw), this._config.watts);
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
          .wfc-light.disabled { cursor:default; opacity:.5; }
          .wfc-calibration { margin-top:14px; font-size:12px; }
          .wfc-calibration summary { cursor:pointer; padding:8px 0; }
          .wfc-calibration button { display:flex; justify-content:space-between; width:100%; padding:9px; margin:3px 0; border:0; border-radius:6px; color:var(--primary-text-color); background:rgba(127,127,127,.08); cursor:pointer; }
          .wfc-calibration p { color:var(--secondary-text-color); }
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
      else if (action === "calibration") this.dispatchEvent(new CustomEvent("hass-more-info", {
        detail: { entityId: value }, bubbles: true, composed: true,
      }));
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
      : st.on === false ? "Off" : "Unknown";

    const modeLights = MODES.map((mode) => {
      const meta = MODE_META[mode];
      const active = st.on && st.mode === mode;
      const bg = active ? `${meta.color}38` : "rgba(127,127,127,.08)";
      const glow = active ? `box-shadow:0 0 14px 3px ${meta.color}a6;` : "";
      const disabled = cfg.managed && mode === "circulate";
      return `
        <div class="wfc-light${disabled ? " disabled" : ""}" ${disabled ? 'aria-disabled="true"' : 'data-action="mode"'} data-value="${mode}">
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
      const disabled = cfg.managed && speed !== "high";
      return `
        <div class="wfc-light${disabled ? " disabled" : ""}" ${disabled ? 'aria-disabled="true"' : 'data-action="speed"'} data-value="${speed}">
          <div class="wfc-dot sm" style="background:${bg};${glow}">
            ${speedBarsSvg(meta.bars, active ? meta.color : dim, dim)}
          </div>
          <div class="wfc-label${active ? " on" : ""}">${meta.label}</div>
        </div>`;
    }).join("");

    const pills = [];
    if (cfg.power_switch && !cfg.managed) {
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
    if (cfg.override_boolean && !cfg.managed) {
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

    const status = cfg.status_sensor ? this._hass.states[cfg.status_sensor] : null;
    const backendError = status?.attributes?.error;
    const validError = backendError && !["unknown", "unavailable"].includes(backendError) ? backendError : "";
    const end = Number(status?.attributes?.cycle_end_timestamp);
    const timedCycle = ["burst", "extension", "extended", "recovery"].includes(status?.attributes?.cycle);
    const deadlineText = timedCycle && end > Date.now() / 1000
      ? new Date(end * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", ...(this._hass.config?.time_zone ? {timeZone:this._hass.config.time_zone} : {}) })
      : "";
    this._root.className = `wfc${this._busy ? " busy" : ""}`;
    this._root.innerHTML = `
      <div class="wfc-header">
        ${iconSvg(MODE_META.exhaust.path, headerColor, 42)}
        <div>
          <div class="wfc-title">${escapeHtml(cfg.name)}</div>
          <div class="wfc-sub">${headerText}</div>
        </div>
      </div>
      <div class="wfc-row">${modeLights}</div>
      <div class="wfc-row">${speedLights}</div>
      ${pills.length ? `<div class="wfc-divider"></div><div class="wfc-pills">${pills.join("")}</div>` : ""}
      ${stats.length ? `<div class="wfc-stats">${stats.join("")}</div>` : ""}
      ${cfg.show_details && status ? `<div class="wfc-busy-note">${escapeHtml(status.state)}</div>` : ''}
      ${cfg.show_details && deadlineText ? `<div class="wfc-busy-note">Until ${escapeHtml(deadlineText)}</div>` : ''}
      ${this._busy ? `<div class="wfc-busy-note">Sending commands…</div>` : ""}
      <div class="wfc-busy-note wfc-error" role="alert"></div>
    `;
    this._root.querySelector(".wfc-error").textContent = this._error || validError || "";
  }

  _statHtml(path, color, value, label) {
    return `
      <div class="wfc-stat">
        ${iconSvg(path, color, 18)}
        <div>
          <div class="wfc-stat-value">${escapeHtml(value)}</div>
          <div class="wfc-stat-label">${label}</div>
        </div>
      </div>`;
  }

  /** Presses the remote the exact number of times needed to reach the
   * target. Passing null for either axis leaves it where it is. */
  async _setState(targetMode, targetSpeed) {
    if (this._busy) return;
    const cfg = this._config;
    this._error = "";
    this._busy = true;
    this._render();
    try {
      if (cfg.setup_mode === "package" && !cfg.controller_script) throw new Error("Select a fan in the card editor.");
      if (cfg.controller_script) {
        if (!this._hass.states[cfg.controller_script]) throw new Error("Fan controller unavailable.");
        if (cfg.managed && (targetMode === "circulate" || (targetSpeed && targetSpeed !== "high"))) return;
        await this._hass.callService("script", cfg.controller_script.slice(7), {
          event: "manual", target_function: targetMode || "",
        });
        return;
      }
      if (!cfg.remote || !cfg.ir_device || !cfg.power_sensor) throw new Error("Complete fan setup in the card editor.");
      let current = this._state();
      if (current.on === null) throw new Error(current.reason);

      if (!current.on) {
        if (cfg.power_switch) {
          await this._hass.callService("switch", "turn_on", {
            entity_id: cfg.power_switch,
          });
          await sleep(cfg.boot_delay * 1000);
        }
        current = await this._waitForState(st => st.on === true);
      }

      const mode = targetMode || current.mode;
      const speed = targetSpeed || current.speed;
      const modePresses = (MODES.indexOf(mode) - MODES.indexOf(current.mode) + 3) % 3;
      const speedPresses = (SPEEDS.indexOf(speed) - SPEEDS.indexOf(current.speed) + 3) % 3;

      await this._press(cfg.mode_command, modePresses);
      await this._press(cfg.speed_command, speedPresses);
      if (modePresses || speedPresses) {
        await this._waitForState(st => st.on && st.mode === mode && st.speed === speed);
      }
    } catch (error) {
      this._error = error.message || String(error);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _waitForState(matches) {
    const timeout = Number(this._config.feedback_timeout);
    const deadline = Date.now() + (Number.isFinite(timeout) && timeout > 0 ? timeout : 20) * 1000;
    do {
      const state = this._state();
      if (matches(state)) return state;
      await sleep(250);
    } while (Date.now() < deadline);
    throw new Error("Fan state was not confirmed. Check the fan and power reading before trying again.");
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
    if (this._config.managed) return;
    this._hass.callService("switch", "toggle", {
      entity_id: this._config.power_switch,
    });
  }

  _toggleOverride() {
    if (this._config.managed) return;
    this._hass.callService("input_boolean", "toggle", {
      entity_id: this._config.override_boolean,
    });
  }
}

// Discover only package state sensors, never arbitrary sensors with similar names.
function discoverFans(hass) {
  return Object.entries(hass?.states || {}).flatMap(([id, entity]) => {
    const a = entity.attributes || {};
    const prefix = a.calibration_prefix;
    if (!id.startsWith('sensor.') || !/^[a-z0-9_]+$/.test(prefix || '') ||
        !/^sensor\.[a-z0-9_]+$/.test(a.power_sensor || '')) return [];
    const script = a.controller_script || `script.${prefix}_set_state`;
    if (!/^script\.[a-z0-9_]+$/.test(script) || !hass.states[script]) return [];
    return [{ state_sensor: id, controller_script: script,
      status_sensor: a.status_sensor || `sensor.${prefix}_control_status`,
      calibration_prefix: prefix, power_sensor: a.power_sensor,
      temperature_sensor: a.temperature_sensor, humidity_sensor: a.humidity_sensor,
      label: (a.friendly_name || prefix.replaceAll('_', ' ')).replace(/ State$/i, '') }];
  }).sort((a, b) => a.label.localeCompare(b.label));
}

function selectedFan(config, fans) {
  if (config.setup_mode === 'standalone') return null;
  if (config.fan_package) return fans.find(f => f.state_sensor === config.fan_package) || null;
  const keys = ['state_sensor', 'controller_script', 'calibration_prefix', 'status_sensor', 'power_sensor'];
  const hints = keys.filter(k => config[k]);
  if (!hints.length) return null;
  const matches = fans.filter(f => hints.every(k => f[k] === config[k]));
  return matches.length === 1 ? matches[0] : null;
}

function resolveConfig(config = {}, hass) {
  const fan = selectedFan(config, discoverFans(hass));
  if (!fan) {
    // A previously selected package must never fall back to direct remote commands.
    if (config.fan_package || config.setup_mode === 'package') {
      return { ...config, setup_mode: 'package', managed: true,
        controller_script: undefined, state_sensor: config.fan_package || config.state_sensor };
    }
    return { ...config };
  }
  const { label, ...links } = fan;
  return { ...config, ...links, fan_package: fan.state_sensor, setup_mode: 'package', managed: true,
    temperature_sensor: config.temperature_sensor ?? fan.temperature_sensor,
    humidity_sensor: config.humidity_sensor ?? fan.humidity_sensor };
}

function sensorField(name, kind, hass, selected) {
  const units = { power: ['W'], temperature: ['°C', '°F'], humidity: ['%'] };
  const ids = Object.entries(hass?.states || {}).filter(([id, s]) => id.startsWith('sensor.') &&
    (s.attributes?.device_class === kind || (!s.attributes?.device_class &&
      (kind !== 'humidity' || /humid/i.test(id + ' ' + (s.attributes?.friendly_name || ''))) &&
      units[kind].includes(s.attributes?.unit_of_measurement)))).map(([id]) => id);
  // Preserve an existing custom sensor even if its integration lacks metadata.
  if (selected && !ids.includes(selected)) ids.push(selected);
  return { name, selector: { entity: { include_entities: ids } } };
}

const WATT_SCHEMA = Object.keys(DEFAULT_WATTS).map(name => ({ name,
  selector: { number: { min: 0, max: 500, step: 0.1, mode: 'box' } } }));
const EDITOR_LABELS = {
  name: 'Card name', power_sensor: 'Power sensor', temperature_sensor: 'Temperature',
  humidity_sensor: 'Humidity', show_details: 'Show automation details',
  power_switch: 'Power switch', remote: 'Remote', ir_device: 'Learned device name',
  mode_command: 'Mode command', speed_command: 'Speed command', press_delay: 'Delay between presses (seconds)',
  feedback_timeout: 'Feedback timeout (seconds)', override_boolean: 'Override helper',
  off_below: 'Off below (W)', max_deviation: 'Allowed difference (W)',
};
for (const mode of MODES) for (const speed of SPEEDS) {
  EDITOR_LABELS[`${mode}_${speed}`] = `${MODE_META[mode].label} ${SPEED_META[speed].label} (W)`;
}

class WindowFanCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  _emit(config) {
    this._config = config;
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config }, bubbles: true, composed: true,
    }));
    this._render();
  }
  _choose(value) {
    const config = { ...this._config };
    // Clear related links as a unit; never carry one room's sensors into another.
    for (const key of ['fan_package','state_sensor','controller_script','status_sensor',
      'calibration_prefix','managed','temperature_sensor','humidity_sensor']) delete config[key];
    if (value === 'standalone') {
      config.setup_mode = 'standalone';
    } else {
      for (const key of ['power_sensor','power_switch','remote','ir_device','override_boolean','watts']) delete config[key];
      config.setup_mode = 'package';
      if (value) config.fan_package = value;
    }
    this._emit(config);
  }
  _updateRanges() {
    for (const row of this._rangeRows || []) {
      const read = key => {
        const raw = this._hass.states[`input_number.${row.prefix}_watts_${key}`]?.state;
        return raw !== undefined && raw !== '' && Number.isFinite(Number(raw)) ? Number(raw) : null;
      };
      const lower = row.index > 0 ? read(RANGE_KEYS[row.index - 1]) : null;
      const upper = row.index < RANGE_KEYS.length ? read(RANGE_KEYS[row.index]) : null;
      row.value.textContent = row.index === 0 ? (upper === null ? 'Unavailable' : `< ${upper} W`)
        : row.index === RANGE_KEYS.length ? (lower === null ? 'Unavailable' : `≥ ${lower} W`)
        : lower === null || upper === null ? 'Unavailable' : `${lower} – < ${upper} W`;
    }
  }
  _form(schema, data, onChange) {
    const form = document.createElement('ha-form');
    form.hass = this._hass; form.schema = schema; form.data = data;
    form.computeLabel = s => EDITOR_LABELS[s.name] || s.name;
    form.addEventListener('value-changed', ev => { ev.stopPropagation(); onChange(ev.detail.value); });
    return form;
  }
  _section(title, node, key) {
    const details = document.createElement('details');
    details.dataset.section = key;
    details.open = this._openSections?.has(key) || false;
    const summary = document.createElement('summary'); summary.textContent = title;
    details.append(summary, node); this.appendChild(details);
  }
  _render() {
    if (!this._config || !this._hass) return;
    const fans = discoverFans(this._hass);
    const fan = selectedFan(this._config, fans);
    const standalone = this._config.setup_mode === 'standalone' ||
      (!fan && !this._config.fan_package && this._config.setup_mode !== 'package' && !!this._config.remote);
    const cfg = resolveConfig(this._config, this._hass);
    // Keep forms/focus intact on ordinary sensor updates; rebuild only for config/discovery changes.
    const signature = JSON.stringify([this._config, fans]);
    if (signature === this._signature) {
      for (const form of this.querySelectorAll('ha-form')) form.hass = this._hass;
      this._updateRanges();
      return;
    }
    this._signature = signature;
    this._openSections = new Set([...this.querySelectorAll('details[open]')].map(d => d.dataset.section));
    this.replaceChildren();
    const style = document.createElement('style');
    style.textContent = 'window-fan-card-editor{display:block} window-fan-card-editor .fan-picker{display:block;margin:12px 0 20px} window-fan-card-editor select{display:block;box-sizing:border-box;width:100%;padding:16px;margin-top:8px;border:1px solid var(--divider-color,#666);border-radius:8px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#222);font:inherit} window-fan-card-editor summary{padding:16px 0;cursor:pointer;font-weight:500} window-fan-card-editor details{border-top:1px solid var(--divider-color,#666);margin-top:12px} window-fan-card-editor .calibration-row{display:flex;justify-content:space-between;width:100%;padding:12px;margin:4px 0;border:0;border-radius:6px;background:var(--secondary-background-color,#eee);color:var(--primary-text-color,#222);font:inherit;cursor:pointer}';
    this.appendChild(style);
    const label = document.createElement('label'); label.className = 'fan-picker'; label.textContent = 'Fan';
    const select = document.createElement('select'); select.setAttribute('aria-label', 'Fan');
    const options = [{ value: '', label: fans.length ? 'Select a fan' : 'No fan packages found' },
      ...fans.map(f => ({ value: f.state_sensor, label: f.label })), { value: 'standalone', label: 'Standalone remote' }];
    if (this._config.fan_package && !fans.some(f => f.state_sensor === this._config.fan_package)) {
      options.push({ value: this._config.fan_package, label: 'Selected fan unavailable' });
    }
    for (const item of options) { const option = document.createElement('option'); option.value = item.value; option.textContent = item.label; select.appendChild(option); }
    select.value = standalone ? 'standalone' : fan?.state_sensor || this._config.fan_package || '';
    select.addEventListener('change', () => this._choose(select.value));
    label.appendChild(select); this.appendChild(label);
    this.appendChild(this._form([{ name: 'name', selector: { text: {} } }], this._config,
      value => this._emit({ ...this._config, name: value.name })));
    if (!standalone && !fan) return;
    const climate = ['temperature_sensor','humidity_sensor'];
    const display = climate.map((key, i) => sensorField(key, i ? 'humidity' : 'temperature', this._hass, cfg[key]));
    display.push({ name: 'show_details', selector: { boolean: {} } });
    this._section('Display options', this._form(display, cfg, value => {
      const next = { ...this._config, show_details: value.show_details };
      for (const key of climate) next[key] = value[key] ?? '';
      this._emit(next);
    }), 'display');
    if (fan) {
      const calibration = document.createElement('div');
      this._rangeRows = [];
      const keys = [...RANGE_KEYS, 'cool_high'];
      for (let i = 0; i < keys.length; i++) {
        const key = keys[i];
        const helperKey = key === 'cool_high' ? 'cool_med_upper' : key;
        const entity = `input_number.${fan.calibration_prefix}_watts_${helperKey}`;
        const button = document.createElement('button'); button.className = 'calibration-row';
        const label = document.createElement('span');
        label.textContent = i === 0 ? 'Off' : key.replace('_upper','').split('_').map(x => x[0].toUpperCase()+x.slice(1)).join(' / ');
        const value = document.createElement('span'); button.append(label, value);
        button.addEventListener('click', () => this.dispatchEvent(new CustomEvent('hass-more-info', {
          detail: { entityId: entity }, bubbles: true, composed: true,
        })));
        this._rangeRows.push({value, index:i, prefix:fan.calibration_prefix});
        calibration.appendChild(button);
      }
      this._updateRanges();
      this._section('Calibration', calibration, 'calibration');
      return;
    }
    this._section('Remote setup', this._form([
      sensorField('power_sensor','power',this._hass,cfg.power_sensor),
      { name: 'remote', selector: { entity: { filter: { domain: 'remote' } } } },
      { name: 'ir_device', selector: { text: {} } },
      { name: 'power_switch', selector: { entity: { filter: { domain: 'switch' } } } },
    ], cfg, value => this._emit({ ...this._config, ...value, setup_mode: 'standalone' })), 'remote');
    this._section('Calibration', this._form(WATT_SCHEMA, { ...DEFAULT_WATTS, ...cfg.watts },
      watts => this._emit({ ...this._config, watts })), 'calibration');
    this._section('Advanced', this._form([
      { name: 'mode_command', selector: { text: {} } },
      { name: 'speed_command', selector: { text: {} } },
      { name: 'press_delay', selector: { number: { min: 0.5, max: 10, step: 0.5, mode: 'box' } } },
      { name: 'feedback_timeout', selector: { number: { min: 1, max: 120, mode: 'box' } } },
      { name: 'override_boolean', selector: { entity: { filter: { domain: 'input_boolean' } } } },
    ], cfg, value => this._emit({ ...this._config, ...value })), 'advanced');
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
