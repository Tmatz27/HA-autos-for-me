/** Den fan dashboard. All requests use the package executor. */
const CARD_VERSION = "1.7.0-dev";

const MODES = ["cool", "exhaust", "circulate"];
const SPEEDS = ["low", "med", "high"];

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
  med: { label: "Medium", color: "#f59e0b", bars: 2 },
  high: { label: "High", color: "#ef4444", bars: 3 },
};

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

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
    this._config = { name: "Den Window Fan", ...resolveConfig(this._sourceConfig, this._hass) };
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
    return { on: null, mode: null, speed: null, reason: "Select the den package in the card editor" };
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
          .wfc.busy { opacity:.8; }
          .wfc-light { border:0; background:none; font:inherit; padding:0; }
          .wfc-recovery { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
          .wfc-confirm { margin-top:12px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
          .wfc-light.disabled { cursor:default; opacity:.5; }
          .wfc-manual-row { display:flex; justify-content:center; align-items:center; gap:12px; margin-top:14px; font-size:13px; color:var(--secondary-text-color); }
          .wfc-manual-row button, .wfc-recovery button, .wfc-confirm button, .wfc-confirm select { border:1px solid var(--divider-color); border-radius:16px; padding:6px 12px; background:transparent; color:var(--primary-text-color); cursor:pointer; font:inherit; }
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
      else if (action === "resume") this._resumeAuto();
      else if (action === "recover") this._request({event:"recover"});
      else if (action === "confirm-open") { this._confirmOpen = !this._confirmOpen; this._render(); }
      else if (action === "confirm") this._confirmPhysical();

    });
    this._root.addEventListener("change", e => {
      if (e.target.dataset.physical === "mode") this._physicalMode = e.target.value;
      if (e.target.dataset.physical === "speed") this._physicalSpeed = e.target.value;
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
      ? `${this._hass.states[cfg.status_sensor]?.attributes?.running === false ? "Stopped · last expected " : this._hass.states[cfg.status_sensor]?.attributes?.confidence !== "established" ? "Expected " : ""}${MODE_META[st.mode].label} • ${SPEED_META[st.speed].label}`
      : st.on === false ? "Off" : "Unknown";

    const modeLights = MODES.map((mode) => {
      const meta = MODE_META[mode];
      const active = st.on && st.mode === mode;
      const bg = active ? `${meta.color}38` : "rgba(127,127,127,.08)";
      const glow = active ? `box-shadow:0 0 14px 3px ${meta.color}a6;` : "";
      const disabled = false;
      return `
        <button type="button" class="wfc-light${disabled ? " disabled" : ""}" ${disabled ? 'aria-disabled="true"' : 'data-action="mode"'} data-value="${mode}">
          <div class="wfc-dot" style="background:${bg};${glow}">
            ${iconSvg(meta.path, active ? meta.color : dim, 26)}
          </div>
          <div class="wfc-label${active ? " on" : ""}">${meta.label}</div>
        </button>`;
    }).join("");

    const speedLights = SPEEDS.map((speed) => {
      const meta = SPEED_META[speed];
      const active = st.on && st.speed === speed;
      const bg = active ? `${meta.color}38` : "rgba(127,127,127,.08)";
      const glow = active ? `box-shadow:0 0 12px 2px ${meta.color}a6;` : "";
      const disabled = false;
      return `
        <button type="button" class="wfc-light${disabled ? " disabled" : ""}" ${disabled ? 'aria-disabled="true"' : 'data-action="speed"'} data-value="${speed}">
          <div class="wfc-dot sm" style="background:${bg};${glow}">
            ${speedBarsSvg(meta.bars, active ? meta.color : dim, dim)}
          </div>
          <div class="wfc-label${active ? " on" : ""}">${meta.label}</div>
        </button>`;
    }).join("");

    const stats = [];
    const power = this._hass.states[cfg.power_sensor];
    stats.push(this._statHtml("M13,2L3,14H11L10,22L21,9H13L13,2Z", "#22c55e",
      power ? `${power.state} ${power.attributes?.unit_of_measurement || "W"}` : "Unavailable", "Fan power"));
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
      ${stats.length ? `<div class="wfc-stats">${stats.join("")}</div>` : ""}
      ${cfg.show_details && status ? `<div class="wfc-busy-note">${escapeHtml(status.state)}</div>` : ''}
      ${cfg.show_details && deadlineText ? `<div class="wfc-busy-note">Until ${escapeHtml(deadlineText)}</div>` : ''}
      <div class="wfc-manual-row"><span>${Number(status?.attributes?.manual_until_timestamp) > Date.now()/1000
        ? `Manual · ${Math.ceil((Number(status.attributes.manual_until_timestamp)-Date.now()/1000)/60)} min`
        : status?.attributes?.blocked ? "Auto paused" : status?.state?.startsWith("Climate unavailable") ? "Auto · climate unavailable" : "Auto"}</span>
        <button type="button" data-action="resume">Resume Auto</button></div>
      <div class="wfc-busy-note">State: ${escapeHtml(status?.attributes?.confidence || "uncertain")} · ${status?.attributes?.command_active ? "Applying setting" : "Idle"}</div>
      <div class="wfc-busy-note">${escapeHtml(status?.attributes?.evidence || "Awaiting controller evidence")}</div>
      <div class="wfc-busy-note">${escapeHtml(status?.attributes?.last_outcome || "")}</div>
      <div class="wfc-recovery">
        <button type="button" data-action="recover">Recover / Reinitialize</button>
        <button type="button" data-action="confirm-open">Confirm Physical State</button>
      </div>
      ${this._confirmOpen ? `<div class="wfc-confirm">
        <span>Select the lights shown on the real fan:</span>
        <select aria-label="Physical mode" data-physical="mode"><option value="">Choose mode</option>${MODES.map(m => `<option value="${m}" ${this._physicalMode === m ? "selected" : ""}>${MODE_META[m].label}</option>`).join("")}</select>
        <select aria-label="Physical speed" data-physical="speed"><option value="">Choose speed</option>${SPEEDS.map(m => `<option value="${m}" ${this._physicalSpeed === m ? "selected" : ""}>${SPEED_META[m].label}</option>`).join("")}</select>
        <button type="button" data-action="confirm">Confirm setting · no IR commands</button>
      </div>` : ""}
      <div class="wfc-busy-note">Recovery: ${escapeHtml(status?.attributes?.recovery || "idle")}</div>
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

  async _setState(targetMode, targetSpeed) {
    return this._request({event:"manual", target_function:targetMode || "", target_speed:targetSpeed || ""});
  }

  async _resumeAuto() { return this._request({event:"resume_auto"}); }

  async _confirmPhysical() {
    if (!MODES.includes(this._physicalMode) || !SPEEDS.includes(this._physicalSpeed)) {
      this._error = "Select both mode and speed shown on the real fan.";
      this._render(); return;
    }
    return this._request({event:"synchronize", target_function:this._physicalMode, target_speed:this._physicalSpeed});
  }

  async _request(data) {
    if (this._busy) return;
    this._busy = true; this._error = ""; this._render();
    let timeout;
    try {
      const script = this._config.controller_script;
      if (!/^script\.[a-z0-9_]+$/.test(script || "") || !this._hass.states[script]) {
        throw new Error("Select the installed den package in the card editor.");
      }
      // script.turn_on acknowledges admission promptly. The backend owns the
      // queue and publishes progress/errors; a browser timeout never resends.
      await Promise.race([
        this._hass.callService("script", "turn_on", {entity_id:script, variables:data}),
        new Promise((_, reject) => { timeout=setTimeout(() => reject(new Error("Home Assistant did not acknowledge the request. Check controller status before retrying.")), 10000); }),
      ]);
    } catch (error) { this._error = error.message || String(error); }
    finally { clearTimeout(timeout); this._busy = false; this._render(); }
  }
}

function discoverFans(hass) {
  const id="sensor.den_fan_state", a=hass?.states?.[id]?.attributes || {};
  if (a.controller_script !== "script.den_fan_set_state" || !hass.states[a.controller_script]) return [];
  return [{state_sensor:id, controller_script:a.controller_script, status_sensor:a.status_sensor,
    power_sensor:a.power_sensor, temperature_sensor:a.temperature_sensor, humidity_sensor:a.humidity_sensor,
    label:"Den Window Fan"}];
}

function resolveConfig(config = {}, hass) {
  const fans=discoverFans(hass);
  const selected=config.fan_package || config.state_sensor || (fans.length === 1 ? fans[0].state_sensor : undefined);
  const fan=fans.find(f => f.state_sensor === selected);
  return {...config, ...fan, setup_mode:"package", managed:true,
    fan_package:selected, controller_script:fan?.controller_script,
    state_sensor:selected, status_sensor:fan?.status_sensor};
}

class WindowFanCardEditor extends HTMLElement {
  setConfig(config) { this._config={...config}; this._render(); }
  set hass(hass) { this._hass=hass; this._render(); }
  _render() {
    if (!this._config || !this._hass) return;
    if (this._form) { this._form.hass=this._hass; return; }
    const form=document.createElement("ha-form");
    form.hass=this._hass;
    form.schema=[{name:"name",selector:{text:{}}},
      {name:"fan_package",selector:{select:{options:[{value:"sensor.den_fan_state",label:"Den Window Fan"}]}}},
      {name:"show_details",selector:{boolean:{}}}];
    form.data={...this._config,fan_package:this._config.fan_package || "sensor.den_fan_state"};
    form.computeLabel=s => ({name:"Card name",fan_package:"Fan package",show_details:"Show climate details"}[s.name]);
    form.addEventListener("value-changed", e => {
      this._config={...e.detail.value,type:"custom:window-fan-card",setup_mode:"package"};
      this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this._config},bubbles:true,composed:true}));
    });
    this.replaceChildren(form); this._form=form;
  }
}

customElements.define("window-fan-card", WindowFanCard);
customElements.define("window-fan-card-editor", WindowFanCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({type:"window-fan-card",name:"Window Fan Card",description:"State-first den fan controls and recovery"});
console.info(`Window Fan Card ${CARD_VERSION}`);
