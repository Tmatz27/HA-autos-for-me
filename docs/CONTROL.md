# Controller reference

## One writer and persistent history

`script.den_fan_set_state` admits requests and reserves manual hold immediately. It performs no hardware operations. It synchronously calls `script.den_fan_executor`, a queued script that exclusively sends fan IR and changes the plug. `script.den_fan_confirm_state` is a convenience wrapper that also enters the same queue. One automation observes sensors and schedules climate evaluation. Do not call the executor directly; use the request service or card.

The executor recomputes Auto after entering the queue. It checks for a newly reserved manual hold before each automatic toggle, and yields between presses without losing completed history. Manual requests wait for the current bounded command/recovery boundary; no requests interleave plug/IR sequences. Repeating an already-satisfied target sends no further toggles. Requests rejected because the finite queue is full are logged by Home Assistant; the package does not automatically replay them.

`input_select.den_fan_confirmed_state` retains its v1.6 ID but stores the expected state. `input_select.den_fan_confidence` is established (user-confirmed or deterministic reset), inferred (service returned or uninterrupted restart restored history), or uncertain (interrupted command, stopped fan or contradiction). `input_boolean.den_fan_running` is a belief, not a hardware sensor. History survives uncertainty instead of being erased. Initial unknown state requires explicit confirmation or recovery. Restart without an incomplete command retains history at inferred confidence and preserves manual/policy deadlines. Offline physical changes with overlapping wattage are undetectable; confirm/recover when the physical remote was used while Home Assistant was down.

An intent marker and last-step message are stored before side effects. A service exception or script cancellation leaves the marker set. The card derives active/busy from the real executor entity, not that marker: it reports interrupted/failed once the executor stops. The next request converts the marker to uncertain/fault and sends no further toggles without reference recovery. Consult the executor trace for the underlying HA exception.

## Supporting wattage

`last_reported` is polled during bounded command windows, including unchanged reports. Fresh compatible bands corroborate history; overlap does not choose a different state or fault. No fresh report yields inferred delivery, with explicit stale/unavailable evidence. A fresh contradiction after the feedback timeout stops remaining presses and requires reference recovery. An inferred starting state with fresh conflicting evidence is blocked before toggles. Explicit physical confirmation or a deterministic reset outweighs a conflicting baseline measurement, but contradictory feedback after another press still stops the sequence. Physical confirmation accepts exactly the selected axes and warns about mismatching wattage. No automatic physical-remote takeover is inferred from watts.

Unchanged watts do not prove receipt; a missed press that stays in overlapping bands cannot be detected with this hardware. The executor limits each request to at most two mode and two speed presses. It does not retransmit a toggle on feedback failure. Recovery sends the startup command exactly once after proved power loss; a failed startup must be inspected before another manual recovery. Optional Auto recovery has one persistent attempt and never resets solely because compatible wattage overlaps.

`off_seconds` is the required discharge interval. The fresh OFF sample may arrive during that interval; change-only meters do not need to emit a second identical zero reading afterward. Fresh startup evidence must arrive after the startup command. A disconnected source that falsely re-reports an old value cannot be distinguished from a measurement; configure availability in the integration and test its cadence.

## Private configuration

Private JSON keys (public values in `DEFAULTS` are examples):

| Key | Meaning |
|---|---|
| `power`, `plug` | Watt sensor and electricity-cutting switch |
| `remote`, `device` | Remote entity and exact learned device group |
| `power_on_command`, `power_off_command` | Exact learned power identifiers; a verified toggle can be both |
| `mode_command`, `speed_command` | Exact learned cyclic commands |
| `temperature`, `humidity` | Actual indoor climate sensor entities; °C/°F normalization is unchanged |
| `manual_minutes` | Hold duration, default 120, 1–1440 minutes |
| `off_seconds`, `plug_delay`, `startup_delay` | Discharge time, wait after plug restoration, wait after startup IR |
| `command_delay` | Minimum time after each mode/speed press |
| `feedback_timeout` | Additional bounded wait for suitable evidence, default 30 seconds |
| `power_stale_seconds` | Evidence age cutoff, default 120 seconds |
| `off_below` | Stopped/running wattage separator; confirm against real hardware |
| `ranges` | All nine measured `[lower, upper]` ranges; overlap is valid |
| `range_tolerance` | Band margin, default 0.5 W |
| `auto_recovery` | Boolean; default false, one persisted attempt if enabled |

No climate thresholds/timers may be changed by this update. They remain the v1.6 values in source. Configuration is emitted throughout templates, statistics sampling, dashboard links, trigger IDs and action targets. Edit private JSON and regenerate; do not hand-replace a few occurrences in YAML.

## Service requests

Call `script.den_fan_set_state` with `event: manual`, `target_function: cool|exhaust|circulate` and/or `target_speed: low|med|high`. An empty axis preserves the known other axis. Unknown state cannot supply a missing axis. Events `resume_auto`, `recover`, and `synchronize` use the same executor. Synchronize requires both axes; recover may specify both or reuse the last requested target (Cool/Low on a fresh installation).

The card uses `script.turn_on` only to admit the request promptly, with `entity_id: script.den_fan_set_state` and `variables` containing these fields. It never directly sends plug or BroadLink commands. A browser transport timeout reports uncertain admission and never automatically retries. Backend errors remain visible through `sensor.den_fan_control_status` even if the dashboard was closed.

## Shared dehumidifier

`dehumidifier_controller.py` and `packages/shared_dehumidifier.yaml` are unchanged. The independent owner uses 50% at night and 60% by day according to `sun.sun`, checks every five minutes and on relevant changes, warns once at 75% tank level and blocks restart commands when full/invalid. Native hardware retains compressor/fan protection. Configure its humidity, tank, device, mode and supported target range using its existing private generator. No fan request writes dehumidifier settings.
