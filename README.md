# HA Autos For Me

Personal Home Assistant automations.

## Bedroom Fan blueprint system

Manages a remote-controlled dual-function window fan (cool/exhaust/circulate,
low/med/high) with no native state feedback, using smart-plug wattage to
decode its real state. Built as reusable **blueprints** so adding another fan
elsewhere in the house is filling out a form, not copy-editing YAML.

### Layout

```
blueprints/
  script/fan_set_state.yaml           <- shared: presses the right buttons to reach a target state
  automation/fan_bedtime_kickoff.yaml <- shared: kicks off "night phase" on a trigger, sets initial state
  automation/fan_night_cycle.yaml     <- shared: cool<->exhaust cycling during night phase
  automation/fan_morning_reset.yaml   <- shared: ends night phase, resets fan
  automation/fan_day_cycle.yaml       <- shared: cool<->exhaust cycling during day phase
fans/
  bedroom/
    helpers.yaml         <- this fan's input_boolean/input_datetime helpers
    template_sensor.yaml <- this fan's wattage->state decoder
    script.yaml           <- this fan's script instance (use_blueprint + inputs)
    automations.yaml       <- this fan's 4 automation instances (use_blueprint + inputs)
    card.yaml              <- this fan's Lovelace control card (Mushroom cards)
```

The blueprints hold all the logic (remote press-counting math, humidity/temp
decision logic, dwell-time debounce). Everything under `fans/<name>/` is just
per-fan configuration: which entities, which thresholds.

### How the bedroom fan's logic flows

1. **Bedtime kickoff** - triggers when the bedroom TV goes `unavailable`
   after 8pm. Clears manual override, sets the fan to cool/high, and flips on
   the night phase.
2. **Night cycle** - while temp is <=62F and humidity is >=75%, switches to
   exhaust to dehumidify. Once temp climbs to >=65F (comfort takes priority
   over humidity while asleep) or humidity drops to <=60%, switches back to
   cool. Speed always stays high. 30 minute minimum gap between switches.
3. **Morning reset** - ends the night phase once outdoor humidity drops
   below 75%, or by 10am at the latest. Resets to cool/high, hands off to the
   day cycle.
4. **Day cycle** - switches to exhaust once humidity is >=68%, back to cool
   once humidity is <=60% or temp is >=75F. Same 30 minute debounce.

Both cycle automations stand down while `input_boolean.bedroom_fan_manual_override`
is on, so pressing a button on the control card doesn't get silently reverted.

### Setup (first time)

1. Copy the whole `blueprints/` folder into your HA config's `blueprints/`
   directory (same relative paths: `config/blueprints/script/...`,
   `config/blueprints/automation/...`).
2. Create the helpers in `fans/bedroom/helpers.yaml` (UI: Settings ->
   Devices & Services -> Helpers, or paste into YAML config).
3. Merge `fans/bedroom/template_sensor.yaml`'s `template:` block into your
   config.
4. Merge `fans/bedroom/script.yaml`'s `script:` block into your config.
5. Add the four automations in `fans/bedroom/automations.yaml` (paste into
   your automations list, or import each individually via the automation
   editor's "Edit in YAML").
6. Add `fans/bedroom/card.yaml` as a card on your dashboard (requires the
   Mushroom cards from HACS). Shows live temp/humidity, current function +
   speed, tap-to-set Cool/Exhaust and Low/Med/High buttons, a manual override
   toggle, and a fan power toggle.
7. **Verify before enabling:**
   - `remote.master_remote` is the correct Broadlink remote entity ID.
   - `Master Fan` / `mode_toggle` / `speed_toggle` match the device + command
     names used when learning the IR codes (power is now handled via the
     plug's switch entity instead of an IR command - see note below).
   - The wattage bands in `template_sensor.yaml` match your fan (measured:
     exhaust low/med/high = 31/33/36W, cool low/med/high = 45/48/51W).
   - `sensor.master_smart_plug_power` and `switch.master_fan_plug` are the
     current correct entity IDs for the plug.

Note: the script now powers the fan on/off via the smart plug's `switch`
entity (deterministic) instead of the remote's `power_toggle` IR command
(a blind toggle), since we have real relay control available. Function and
speed still have to go through the IR remote since there's no direct switch
equivalent for those.

### Adding a new fan

1. Duplicate `fans/bedroom/` to `fans/<new-fan-name>/`.
2. In `helpers.yaml`: rename the three helper entity ids/names.
3. In `template_sensor.yaml`: rename the sensor, and re-measure that fan's
   own wattage per function/speed combo (unplug nothing needed - just cycle
   through cool low/med/high and exhaust low/med/high while watching the
   plug's power sensor, same way the bedroom fan's bands were derived) and
   adjust the band boundaries.
4. In `script.yaml`: point `remote_entity`, `ir_device_name`,
   `power_switch_entity`, `fan_state_sensor`, and `last_command_datetime` at
   the new fan's entities. Rename the script's key/alias.
5. In `automations.yaml`: point every input at the new fan's entities/helpers
   and script, and adjust thresholds/times/trigger entity as needed for that
   room. Give each automation a unique `id`.
6. In `card.yaml`: swap every entity id for the new fan's, rename the title.
7. Merge/import all the above into your HA config like the first-time setup
   steps above (steps 2-6), minus re-copying `blueprints/` (already shared).

Lovelace has no blueprint/input system, so the card stays a copy-and-replace
file per fan - there's no way to parametrize it the way the automations/
script are parametrized.

### Known assumptions worth revisiting

- Circulate is treated as a single catch-all wattage band since it's never
  intentionally targeted - if the fan somehow lands there (e.g. manual
  remote use outside this system), the script still correctly computes the
  presses needed to reach cool or exhaust from circulate.
- Thresholds are per-fan blueprint inputs (not hard-coded), so tuning a
  single fan's behavior means editing that fan's `automations.yaml`, not the
  blueprint.
