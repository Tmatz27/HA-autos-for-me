# HA Autos For Me

Personal Home Assistant automations.

## Bedroom Fan (window dual-fan, cool/exhaust/circulate)

Files:
- `bedroom_fan/template_sensors.yaml` - decodes the fan's actual function +
  speed from smart plug wattage (no remote feedback exists otherwise).
- `bedroom_fan/helpers.yaml` - the `input_boolean` (night/day phase) and
  `input_datetime` (debounce timestamp) the automations rely on.
- `bedroom_fan/scripts.yaml` - `script.bedroom_fan_set_state`, the single
  place that sends Broadlink IR commands. Computes exactly how many times to
  press mode/speed from the current decoded state.
- `automations/bedroom_fan_bedtime_kickoff.yaml`
- `automations/bedroom_fan_night_cycle.yaml`
- `automations/bedroom_fan_morning_reset.yaml`
- `automations/bedroom_fan_day_cycle.yaml`

### How the logic flows

1. **Bedtime kickoff** - triggers when the bedroom TV goes `unavailable`
   after 8pm (mirrors the existing TV-off hatch routine trigger style). Sets
   the fan to cool/high and flips on the night phase.
2. **Night cycle** - while temp is <=62F and humidity is >=75%, switches to
   exhaust to dehumidify. Once temp climbs to >=65F (comfort takes priority
   over humidity while asleep) or humidity drops to <=60%, switches back to
   cool. Speed is always forced to high. A 30 minute minimum gap between
   switches avoids repeated beeping overnight.
3. **Morning reset** - ends the night phase once outdoor humidity
   (`sensor.aso_vandenberg_humidity`) drops below 75%, or by 10am at the
   latest if it hasn't. Resets to cool/high and hands off to the day cycle.
4. **Day cycle** - keeps the fan on exhaust once humidity is >=68%, back to
   cool once humidity is <=60% or temp is >=75F. Same 30 minute debounce.

### Setup

1. Create the helpers in `bedroom_fan/helpers.yaml` (either paste into your
   YAML config or create via Settings -> Devices & Services -> Helpers).
2. Merge `bedroom_fan/template_sensors.yaml`'s `template:` block into your
   config.
3. Merge `bedroom_fan/scripts.yaml`'s `script:` block into your config.
4. Copy the four automation files into your `automations/` directory (or
   import each via the automation editor's YAML mode).
5. **Verify before enabling:**
   - `remote.master_remote` is the correct entity ID for the Broadlink remote
     that controls the bedroom/master fan (confirm in Developer Tools ->
     States - it was inferred from the friendly name "master remote").
   - `Master Fan` / `power_toggle` / `mode_toggle` / `speed_toggle` match
     the device + command names you used when learning the IR codes.
   - The wattage bands in `template_sensors.yaml` match your fan (measured:
     exhaust low/med/high = 31/33/36W, cool low/med/high = 45/48/51W).
   - `sensor.master_smart_plug_power` is the current correct entity ID for
     the plug's power sensor (this was renamed once already).

### Known assumptions worth revisiting

- Circulate is treated as a single catch-all band (~38-43.5W) since it's
  never intentionally targeted - if the fan somehow lands there (e.g.
  manual remote use), the script will still correctly compute the presses
  needed to get to cool or exhaust from circulate.
- All thresholds (62/65F, 60/75/68% humidity, 30 min debounce, 75% outdoor
  humidity, 10am fallback) are hard-coded per current requirements rather
  than exposed as adjustable helpers - easy to promote to `input_number`
  helpers later if you want to tune them from the dashboard instead of
  editing YAML.
