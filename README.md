# Window Fan Card and Climate Control

A Home Assistant dashboard card and two configurable packages for a dual window fan controlled by a Broadlink remote. A smart plug supplies measured power feedback for all nine combinations of Cool, Exhaust and Circulate at Low, Medium and High speed.

Version **1.4.0** reduces climate control to three rules, shared by both rooms: exhaust at or above 65% humidity, cool at or below 62% when the room is warmer than 72F, otherwise leave the fan alone. Cooling bursts, recovery windows, outdoor-humidity protection and morning drying are gone - those mechanisms each requested a different mode and their interactions were what made the fan cycle. The bedroom keeps one override, a sleep lock. All entity IDs and hardware settings in this repository are examples. Configure them before installation.

## Card setup

Open the visual card editor and choose **Bedroom Fan** or **Den Fan** under **Fan**. Only installed fan packages appear. The controller, state, calibration and room sensors are linked automatically; no script or state-sensor pickers are needed. Set the card name if desired. **Display options** and **Calibration** stay collapsed until needed.

The dashboard shows mode, speed, temperature, humidity and Auto/manual-hold status. All six mode/speed buttons work. Each selection holds for 30 minutes, then the climate policy resumes at High; **Resume Auto** ends the hold early. Calibration instructions and controls are kept in the editor; routine automation text is hidden unless **Show automation details** is enabled. Real command errors still appear.

Update the card and both packages together for manual controls; the card reports a package-upgrade requirement when it finds an older controller. Existing linked card configurations continue to work. Partially configured cards are matched only when their selected power sensor and any package references agree on exactly one package. If multiple packages match, select the intended fan explicitly. Older v1.2.0 packages can be detected; update their YAML to auto-fill room sensors, or keep the existing display sensor selections. Temperature, humidity and power pickers show relevant sensors instead of every sensor.

**Standalone remote** is a separate choice for installations without a package. Remote settings, calibration and advanced timing controls are grouped separately. In standalone mode, measure all nine operating states before sending commands.

## Card and packages

- The standalone card editor exposes all nine measured wattages, including Circulate. Missing or ambiguous calibration reports Unknown instead of inventing a state.
- The managed card reads the package's state sensor; its editor opens the shared wattage helpers. Card requests and automations use the same serialized controller.
- Automatic policies use High speed and never turn the fan off. Manual controls support all nine running states and bypass climate decisions for 30 minutes.
- The controller checks fresh power feedback after each independent mode or speed press. An unconfirmed press stops the sequence and reports an error; retries are limited to once per five minutes.
- Absolute deadlines preserve the sleep lock and manual holds across restarts. Missing sensor readings have explicit fallbacks.

## Install or upgrade

Use Home Assistant 2024.10 or newer for these packages; they use the [modern automation YAML syntax](https://www.home-assistant.io/blog/2024/10/02/release-202410/#improved-yaml-syntax-for-automations).

1. Back up existing fan packages and dashboard configuration. Replace old fan packages and disable separately copied legacy automations so each fan has one controller.
2. Configure the external entities and learned Broadlink device/command names in `HARDWARE` and `cfg` in `build.py`. Replace `media_player.bedtime_tv` with the desired TV entity. Set the schedule and climate limits there, then run `python build.py`. This updates every embedded reference consistently. Alternatively replace each placeholder throughout the generated YAML, including triggers, templates and action targets; editing only `cfg` is insufficient for hardware remapping.
3. Measure all nine operating states and configure calibration. The included numeric bands are examples, not universal fan specifications. See [calibration and controller settings](docs/CONTROL.md).
4. Copy the selected generated files from `packages/` into the Home Assistant packages directory. Enable [packages](https://www.home-assistant.io/docs/configuration/packages/) if necessary:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

5. Install `dist/window-fan-card.js` as a JavaScript module dashboard resource, or update the existing HACS custom repository installation. The release includes the same `window-fan-card.js` asset. Keep one resource URL and hard-refresh the dashboard; the browser console should show 1.4.0.
6. Run Home Assistant's configuration check and restart. Select the fan in the visual card editor, or use the short YAML from `examples/`. Verify that `sensor.bedroom_fan_state`, `sensor.den_fan_state` and the corresponding control-status sensors have the expected IDs; resolve any duplicate entity suffixes consistently.
7. Observe the first complete control cycle and adjust calibration/timing to the fan and smart plug. Software tests do not replace checking the installation against physical equipment.

The packages and managed card should be upgraded together. The old setup generator has been replaced with an updated [setup guide](https://tmatz27.github.io/HA-autos-for-me/setup.html); generated settings now come from the versioned Python builder.

## Example policies

Both rooms run the same three rules: **exhaust** at or above 65% RH, **cool** at
or below 62% RH when the room is warmer than 72F, and otherwise **hold** whatever
is already running. The 62-65% gap is deliberate - cooling raises room humidity
by a couple of points on its own, so a single threshold makes Cool and Exhaust
trigger each other. A mode change is held for at least 20 minutes because the fan
beeps on every press.

The bedroom adds a sleep lock: a TV transition to off/standby/unavailable, a
manual Cool selection, or the window opening at 22:00 with the TV already off
holds Cool/High until morning with no mode changes at all.

The den runs the same three rules with no sleep lock.

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
node tests/card.test.cjs
```

`build.py` and `templates/` are the package sources. The builder generates `packages/` and `examples/`; the test module imports it and regenerates these files before testing. Maintain the card directly in `dist/window-fan-card.js`. Tests execute the generated controller with simulated motor transitions and delayed power reports, and exercise policy decisions and card behavior. They do not start a Home Assistant instance.

Publish only generalized examples. Keep installation-specific entity IDs, remote device names, locations, screenshots and schedules out of commits and release attachments.
