# Window Fan Card and Climate Control

A Home Assistant dashboard card and two configurable packages for a dual window fan controlled by a Broadlink remote. A smart plug supplies measured power feedback for all nine combinations of Cool, Exhaust and Circulate at Low, Medium and High speed.

Version **1.6.0** adds humidity-aware comfort cooling for the den and an optional shared dehumidifier package. The den targets 68°F with a dynamic drying threshold, a 65% ordinary RH ceiling and sustained heat relief at 78°F until 75°F. The dehumidifier targets 50% at night and 60% by day, with tank warnings. Bedroom control remains unchanged. All public mappings are configurable examples.

## Card setup

Open the visual card editor and choose **Bedroom Fan** or **Den Fan** under **Fan**. Only installed fan packages appear. The controller, state, calibration and room sensors are linked automatically; no script or state-sensor pickers are needed. Set the card name if desired. **Display options** and **Calibration** stay collapsed until needed.

The dashboard shows mode, speed, temperature, humidity and Auto/manual-hold status. All six mode/speed buttons work. Den selections hold for 120 minutes; bedroom selections hold for 30 minutes, then the climate policy resumes at High; **Resume Auto** ends the hold early. Calibration instructions and controls are kept in the editor; routine automation text is hidden unless **Show automation details** is enabled. Real command errors still appear.

For this update, replace the den package and card together; leave the installed bedroom package in place. The card reports a package-upgrade requirement when it finds an older controller. Existing linked card configurations continue to work. Partially configured cards are matched only when their selected power sensor and any package references agree on exactly one package. If multiple packages match, select the intended fan explicitly. Older v1.2.0 packages can be detected; update their YAML to auto-fill room sensors, or keep the existing display sensor selections. Temperature, humidity and power pickers show relevant sensors instead of every sensor.

**Standalone remote** is a separate choice for installations without a package. Remote settings, calibration and advanced timing controls are grouped separately. In standalone mode, measure all nine operating states before sending commands.

## Card and packages

- The standalone card editor exposes all nine measured wattages, including Circulate. Missing or ambiguous calibration reports Unknown instead of inventing a state.
- The managed card reads the package's state sensor; its editor displays the den ranges or opens bedroom wattage helpers. Den physical-state confirmation is available in the editor. Card requests and automations use the same serialized controller.
- Automatic policies use High speed and never turn the fan off. Manual controls support all nine running states and bypass climate decisions for 120 minutes in the den and 30 minutes in the bedroom.
- The controller checks fresh power feedback after each independent mode or speed press. An unconfirmed press stops the sequence and reports an error; the den latches a fault until an explicit recovery request or confirmed physical startup. The existing bedroom driver retains its five-minute retry interval.
- Absolute deadlines preserve the sleep lock and manual holds across restarts. Missing sensor readings have explicit fallbacks.

## Install or upgrade

Use Home Assistant 2024.10 or newer for these packages; they use the [modern automation YAML syntax](https://www.home-assistant.io/blog/2024/10/02/release-202410/#improved-yaml-syntax-for-automations).

1. Back up existing fan packages and dashboard configuration. Replace old fan packages and disable separately copied legacy automations so each fan has one controller.
2. Configure the external entities and learned Broadlink device/command names in `HARDWARE` and `cfg` in `build.py`. Replace `media_player.bedtime_tv` with the desired TV entity. For den ranges, startup reference and timing, configure `den_controller.py` (or pass a private JSON config to its CLI). Set bedroom schedule and climate limits in `build.py`, then run `python build.py`. This updates every embedded reference consistently. Alternatively replace each placeholder throughout the generated YAML, including triggers, templates and action targets; editing only `cfg` is insufficient for hardware remapping.
3. Measure all nine operating states and configure calibration. The included numeric bands are examples, not universal fan specifications. See [calibration and controller settings](docs/CONTROL.md).
4. Copy the selected generated files from `packages/` into the Home Assistant packages directory. Enable [packages](https://www.home-assistant.io/docs/configuration/packages/) if necessary:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

5. Install `dist/window-fan-card.js` as a JavaScript module dashboard resource, or update the existing HACS custom repository installation. The release includes the same `window-fan-card.js` asset. Keep one resource URL and hard-refresh the dashboard; the browser console should show 1.6.0.
6. Run Home Assistant's configuration check and restart. Select the fan in the visual card editor, or use the short YAML from `examples/`. Verify that `sensor.bedroom_fan_state`, `sensor.den_fan_state` and the corresponding control-status sensors have the expected IDs; resolve any duplicate entity suffixes consistently.
7. Observe the first complete control cycle and adjust calibration/timing to the fan and smart plug. Software tests do not replace checking the installation against physical equipment.

The packages and managed card should be upgraded together. The old setup generator has been replaced with an updated [setup guide](https://tmatz27.github.io/HA-autos-for-me/setup.html); generated settings now come from the versioned Python builder.

For a shared dehumidifier, configure `dehumidifier_controller.py` or run `python dehumidifier_controller.py --config PRIVATE.json --output shared_dehumidifier.yaml`. Install that package once and disable any other automation that writes its settings. The 50% night / 60% day schedule follows `sun.sun`, checks every five minutes and reacts to sunrise/sunset. The appliance retains control of its compressor and fan speed. Read the [dehumidifier setup](docs/CONTROL.md#shared-dehumidifier) before enabling it.

## Example policies

**Den:** Automatic speed is High. Ordinary cooling starts at 70°F when humidity is at or below the restart limit: 58% through 72°F, 60% at 74°F, 62% at 76°F, and 65% at 78°F, interpolated between points. Once started, cooling continues toward 68°F until RH reaches 65% or rises by more than eight percentage points from a recorded low within the preceding ten minutes. Drying requires at least ten minutes of Exhaust and continues until the temperature-dependent humidity limit is met. There is no maximum drying time.

At 78°F, heat priority immediately overrides ordinary humidity limits, the rapid-rise guard and the Exhaust recovery timer. Cool/High stays latched until temperature reaches 75°F. At 75°F the ordinary cooling stop conditions apply; if humidity is acceptable, cooling may continue toward 68°F. Thirty-minute deadlines are reassessment points, not forced mode changes. A two-hour manual hold still overrides all automatic output. Ordinary decisions need valid indoor temperature and humidity; heat priority may run without a humidity reading when temperature is valid. Neither outdoor temperature nor outdoor relative humidity blocks cooling. No outdoor measurements are required by this policy.

The ten-minute humidity minimum uses a valid indoor humidity sample refreshed at least once per minute, including unchanged readings. Sensor availability must reflect disconnection; an available but stale source cannot be distinguished from an unchanged measurement. The 65% stop remains active while a new history window warms up. Climate evaluation runs once per minute; no continuous climate polling is used.

**Bedroom (unchanged):** Exhaust at RH ≥65%, Cool at RH ≤62% and temperature >72°F, otherwise hold the running mode, with a 20-minute minimum mode interval. The existing sleep lock holds Cool/High until morning. See [bedroom configuration](docs/CONTROL.md) for its existing schedule and triggers.

Outdoor readings are not used for control. Exhaust removes moisture only when
the replacement air is drier, which depends on the airflow path through the
house rather than on outdoor humidity at the window. These controls cannot
guarantee room limits.

See [CONTROL.md](docs/CONTROL.md) for the exact sample thresholds, calibration behavior, timing and limitations.

## Development

Python 3.11+ and Node.js 20+ are sufficient for the software checks:

```sh
python -m pip install -r requirements-test.txt
python build.py
python tests/test_control.py
python tests/test_dehumidifier.py
node tests/card.test.cjs
```

`build.py` and `templates/` are the bedroom sources; `den_controller.py` is the den source. The builder generates `packages/` and `examples/`; the test module imports it and regenerates these files before testing. Maintain the card directly in `dist/window-fan-card.js`. Tests execute the generated controller with simulated motor transitions and delayed power reports, and exercise policy decisions and card behavior. They do not start a Home Assistant instance.

Publish only generalized examples. Keep installation-specific entity IDs, remote device names, locations, screenshots and schedules out of commits and release attachments.
