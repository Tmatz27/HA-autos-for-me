# Home Assistant automation project

Repository: https://github.com/Tmatz27/HA-autos-for-me

This public handoff contains reusable technical context and example settings.
It intentionally omits the household's location, daily routine, exact installed
versions, and actual entity IDs. Configure personal values locally in Home Assistant.
Example times are defaults to customize, not statements about occupancy.

## Repository scope

Use this repository for multiple Home Assistant automations, organized by feature.
The first feature controls a dual-motor IR window fan. Keep the existing card paths
stable. A separately distributed card can be split out later if useful.

## Desired fan behavior — still to be implemented

- Prioritize cool/intake while the configured sleep phase is active.
- Start a drying phase at a configurable morning time; 05:00 is an example.
- Exhaust when the replacement air offers useful drying, then permit intake when
  outdoor conditions improve.
- Before the sleep phase, prefer exhaust when outdoor relative humidity exceeds
  room relative humidity. Evaluate dew point as an additional intake criterion.
- Support a configurable bedtime trigger, such as a selected TV becoming
  unavailable. It clears manual override, starts cool/high, and enters sleep mode.
- Example comfort targets: <=70 F for sleep preparation, <=60% RH for daytime
  drying, and a configurable daytime temperature limit in the 73–75 F range.
  The temperature-versus-humidity conflict policy still needs tuning.
- Use HIGH whenever running. Manual Off is allowed. Manual choices last until
  Auto is selected or the configured bedtime trigger resets override.
- Send a dehumidifier suggestion only when daytime ventilation is insufficient:
  phone notification plus Home Assistant persistent notification. The sample
  action is `notify.insert_here`; replace it locally. Alert persistence and
  repeat suppression still need implementation.
- Show actual fan state, Auto/Manual, phase, reason, readings, and settings on a
  dashboard card. Avoid assuming that requested state equals physical state.
- Limit unnecessary IR presses because the fan beeps. No hardware modification
  is required.

## Guided setup direction

An automation blueprint can offer grouped form inputs for hardware, sensors,
timing, comfort targets, override helpers, and notification actions. This is the
current setup direction under consideration; the earlier blanket rejection of
blueprints no longer applies.

An automation blueprint creates an automation from supplied inputs. It does not
install a dashboard custom card or provision an entire package of helpers,
template sensors, and scripts. Design a small one-time controller/helper setup
plus a guided policy blueprint, and reuse the same controller from the card.
Avoid enabling both the old package automations and the new blueprint controller.

Actual entity selections and schedule choices should remain in the locally
created Home Assistant automation, not in this public repository. Blueprint
implementation has not been completed.

References:
- https://www.home-assistant.io/docs/blueprint/schema/
- https://www.home-assistant.io/docs/blueprint/selectors/
- https://www.home-assistant.io/docs/automation/using_blueprints/

## Existing implementation

- `dist/window-fan-card.js`: custom dashboard card, visual configuration,
  wattage-based decoding, direct IR commands, power and override controls.
- `packages/window_fan_bedroom.yaml`: two booleans, one datetime helper, state
  sensor, command script, and four legacy automations.
- `docs/setup.html`: entity/wattage configuration form generating card and package YAML.
- `hacs.json`: distribution metadata.
- Learned IR commands have been reported working. Runtime logs now confirm that
  the package automations are installed, but complete hardware validation remains
  outstanding. Do not equate automation execution with correct fan behavior.
- Previous simulation results were reported as 10/10 decodes, 7/7 press sequences,
  and 13/13 generated-template band checks. They were not rerun for this handoff.

The existing package still uses legacy temperature/humidity cycles and an outdoor
humidity/clock morning reset. It does not implement the desired morning drying
schedule, evening protection, or dehumidifier advisory above.

## Hardware model and calibration examples

Mode cycles cool -> exhaust -> circulate -> cool.
Speed cycles low -> med -> high -> low.
Exhaust -> cool takes two mode presses. Circulate is a transit state.
Recorded startup behavior is cool/low, but verify power restoration on each unit.
A plug already ON does not imply the fan is running after an IR power toggle.

| Mode | Low | Medium | High |
| --- | --- | --- | --- |
| Cool | 45 W | 48 W | 51 W |
| Exhaust | 31 W | 33 W | 36 W |
| Circulate, estimated | 38 W | 40.5 W | 43.5 W |

These are calibration examples. Circulate readings are inferred averages and
need measurement. Validate fluctuations, transition readings, reporting latency,
and the current two-second inter-press delay.

Generic configuration placeholders:

| Purpose | Example |
| --- | --- |
| Plug power | sensor.fan_power |
| Plug switch | switch.fan_plug |
| IR remote | remote.fan_remote |
| IR device | Window Fan |
| IR commands | power_toggle, mode_toggle, speed_toggle |
| Room temperature | sensor.bedroom_temperature |
| Room RH | sensor.bedroom_humidity |
| Outdoor temperature | sensor.outdoor_temperature |
| Outdoor RH | sensor.outdoor_humidity |
| Bedtime trigger entity | media_player.bedtime_tv |
| Phone notification | notify.insert_here |

## Reliability gaps

The night/day dwell checks previously subtracted a timezone-naive parsed helper
value from timezone-aware now(), causing condition errors. They now subtract the
helper's numeric timestamp attribute from now().timestamp(); the setup generator
uses the same fix. A missing timestamp defaults to zero, preserving the previous
behavior of permitting an initial command when no last-command value is available.

1. Legacy morning reset ignores manual override; only the bedtime reset should
   intentionally clear it under the desired policy.
2. HIGH is requested on commands but is not continuously enforced. The current
   card allows lower speeds and preserves speed on a mode-only request.
3. Card commands bypass the backend script queue and dwell timestamp. Separate
   dashboards and automations can issue overlapping IR sequences.
4. Commands are calculated from an initial reading without final target
   confirmation or bounded recovery for missed IR.
5. Missing power readings can be treated as off; the YAML startup wait can time
   out and continue. Handle unavailable, stale, and ambiguous readings explicitly.
6. Dwell applies only to the legacy night/day cycles. Dwell expiry alone does not
   trigger reevaluation; restart/resume handling is incomplete.
7. Legacy daytime branches can alternate under simultaneous high RH and high
   temperature. Define explicit priority and hysteresis.
8. Moisture comparison and dehumidifier notifications are not implemented.

## Airflow and humidity

Exhaust only helps drying if replacement air is drier. A typical useful setup
draws house air through an open door; verify the actual airflow path locally.
A house temperature/RH sensor can help quantify that benefit but is optional.
Outdoor weather-station readings may differ from conditions at the window.

Compare dew points derived from temperature/RH to assess incoming moisture.
Use room RH for the dryness target. Lower outdoor RH alone does not establish
lower moisture content. A single low-RH reading does not prove textiles are dry.
Reference: https://www.weather.gov/arx/why_dewpoint_vs_humidity

Reaching a bedtime temperature target depends on available cooling time and
conditions. Do not guarantee it or silently override humidity protection to
achieve it. Tune from measured temperature and moisture trends.

## Next steps

1. Design the blueprint form and one-time controller/helper setup.
2. Validate physical states, startup behavior, watts, sensor latency, and IR timing.
3. Implement one serialized controller with feedback confirmation, manual override,
   HIGH enforcement, and bounded error handling.
4. Implement the policy blueprint and update card integration and setup guidance.
5. Test schedule boundaries, restarts, sensor failures, manual Off, and missed IR.
6. Observe real overnight/daytime behavior and tune; then configure additional fans.

## Publication and privacy

The documentation handoff was merged and released as `v1.0.0`. An older release
has tag `V0.1.0` despite a title containing "v1.0.0". Neither proves hardware
validation or completion of the newly requested behavior.

Generalizing current files does not erase earlier commits, pull request diffs,
tags, release source archives, or external copies. Historical removal requires
a separate, explicitly scoped cleanup. Do not claim the repository's history
is anonymized merely because the current files use examples.
