# Home Assistant project handoff

Repository: https://github.com/Tmatz27/HA-autos-for-me

Prepared September 15, 2026 after reading main's README.md, CLAUDE.md,
packages/window_fan_bedroom.yaml, dist/window-fan-card.js, docs/setup.html,
and hacs.json. This context distinguishes confirmed requirements from existing
implementation. The handoff update changes documentation only; no Home Assistant
configuration was changed or tested.

## Project scope

Keep this repository for multiple personal Home Assistant automations over time.
Organize each feature as a named package plus its documentation and relevant tests.
The bedroom fan is the first feature. Keep the existing card paths stable for now.
A separately distributed reusable card could later have its own repository, but
there is no need to split every personal automation into a separate repository.
Home Assistant supports grouping related integrations and automations in packages:
https://www.home-assistant.io/docs/configuration/packages/

## Latest user goals — supersede the older agreed thresholds

- Keep the master bedroom comfortable at Vandenberg, where humidity is high.
- Run cool/intake through the sleeping period until 5:00 a.m. local time.
  Overnight cooling takes priority over drying, even if bedroom RH exceeds 70%.
- At 5:00 a.m., switch to exhaust for the morning/daytime drying period when in
  Auto. The room is very cool then; occupants usually wake between 6 and 8 a.m.
  Some warming during exhaust is expected and acceptable.
- Keep exhaust until outdoor conditions improve enough to return to cool/intake.
  The user's criterion is outdoor humidity becoming normal and lower than bedroom
  humidity. Refine intake eligibility with a moisture comparison, without silently
  discarding the user's evening humidity protection rule below.
- Before bedtime, switch to exhaust when outdoor RH exceeds bedroom RH. Outdoor
  RH rises above 90% around sunset and intake makes the sheets feel damp quickly.
  Keep this evening protection until the TV-based bedtime trigger starts cooling.
- Keep the existing TV-based bedtime trigger: TV becoming unavailable indicates
  living-room cleanup and getting ready for bed. It should clear manual override
  (including manual Off), start cool/high, and begin the overnight phase.
- Aim for bedroom temperature <=70 F by bedtime, usually around 9 p.m. General
  daytime preference is below 75 F, possibly 73 F; use 73 F only as a tentative
  tuning target, not a user-confirmed hard limit. Daytime humidity target is <=60%.
  Overnight cooling priority remains in effect even when that RH target is missed.
- Always use HIGH while running. Intentional manual OFF is explicitly allowed;
  keep manual choices until the user selects Auto or the bedtime trigger resets
  override. The 5 a.m. transition must respect an active manual override.
- Reduce persistent dampness in bedding and clothing during the day.
- Suggest bringing in the portable dehumidifier as a last resort when ventilation
  cannot achieve the <=60% humidity target. Send a phone push notification AND a
  persistent notification in Home Assistant. Notification only; no automatic
  dehumidifier control has been requested. Use `notify.insert_here` as the phone
  notification action placeholder; the user will replace it with their actual
  action. Do not block implementation or ask again for the phone action name.
  The alert persistence interval remains to be determined.
- Provide a dashboard card for status, manual mode override, returning to Auto,
  and viewing settings from other Home Assistant dashboards/devices.
- The fan still beeps. The user could not open it because brackets blocked access.
  Do not make completion depend on disabling the beeper.

## Accomplished and verified by repository inspection

- Broadlink remote codes are learned and work, according to the user.
- Indoor and outdoor temperature/humidity readings are available, per user.
- User explicitly confirms neither this card nor this package is installed yet.
  Outdoor readings come from a weather station approximately one mile away; a
  local outdoor sensor is planned but is not a prerequisite for initial setup.
- dist/window-fan-card.js: custom dashboard card with entity configuration,
  wattage-based mode/speed display, direct IR commands, power and override controls.
- packages/window_fan_bedroom.yaml: two boolean helpers, one datetime helper,
  decoded-state sensor, command script, and four automations.
- docs/setup.html: entity/wattage configuration page that generates card/package YAML.
- hacs.json: card distribution metadata exists. Installation/release success has
  not been verified in this review.
- The prior handoff reports simulated checks: 10/10 decodes, 7/7 press sequences,
  13/13 generated-template band checks. These were not rerun in this review and
  are not evidence of real-hardware reliability.
- Earlier notes say the complete controller has never been tested against the
  physical fan. Working learned IR commands do not establish end-to-end success.

## Hardware and known entities

Home Assistant versions confirmed by the user's screenshot:

- Installation method: Home Assistant OS
- Core: 2026.9.2
- Supervisor: 2026.09.0
- Operating System: 18.2
- Frontend: 20260826.7

Mode cycles cool -> exhaust -> circulate -> cool. Speed cycles low -> med -> high.
Exhaust -> cool needs two mode presses. Circulate is a transit state, not a desired
operating mode. Recorded power-on behavior is cool/low; verify plug power restoration.
Power control currently uses the smart plug. A plug already ON does not establish
that the fan is running if someone used the IR power toggle.

Recorded wattages:

| Mode | Low | Medium | High |
| --- | --- | --- | --- |
| Cool | 45 W | 48 W | 51 W |
| Exhaust | 31 W | 33 W | 36 W |
| Circulate, estimated only | 38 W | 40.5 W | 43.5 W |

Circulate values are inferred averages, not measurements. Verify all states,
normal fluctuations, transition readings, and sensor reporting latency.

| Purpose | Existing entity/name |
| --- | --- |
| Plug power | sensor.master_smart_plug_power |
| Plug switch | switch.master_fan_plug |
| Broadlink | remote.master_remote |
| IR device | Master Fan |
| Commands | power_toggle, mode_toggle, speed_toggle |
| Bedroom temperature | sensor.master_air_quality_temperature |
| Bedroom RH | sensor.master_air_quality_humidity |
| Outdoor temperature | sensor.aso_vandenberg_temperature |
| Outdoor RH | sensor.aso_vandenberg_humidity |
| Bedtime TV | media_player.lg_webos_tv_oled65c2pua |

Plug is documented as a Shelly Plug US Gen4 over Matter. Power sensor was renamed
previously. Confirm these IDs and temperature units rather than asking the user
to rediscover everything. The outdoor weather-station readings are a proxy for
window conditions, so allow for local differences when tuning the controls.

## Existing behavior and gaps

Current YAML uses the OLD policy: TV unavailable after 8 p.m. starts cool/high;
night exhaust at <=62 F and >=75% RH; back to cool at >=65 F or <=60% RH;
morning resets to cool when outdoor RH crosses below 75% or at 10 a.m.; daytime
exhaust at >=68% RH and cool at <=60% RH or >=75 F. There is no 5 a.m. transition.
Do not carry these thresholds forward as newly approved requirements.

Inspection found:

1. Manual override only blocks the night/day cycle automations. Morning reset
   ignores it; bedtime explicitly clears it. Latest decision: manual override
   persists until Auto is selected or bedtime; other transitions must respect it.
2. HIGH is requested on automated commands, but there is no continuous correction
   for a physical remote speed change. Card buttons allow low/medium and a mode
   click preserves the existing speed.
3. The card sends IR independently of the queued backend script. Its busy flag
   only protects that card instance; it does not serialize other dashboards or
   automations, and card commands do not update the backend dwell timestamp.
4. Both implementations calculate a press sequence from an initial reading and
   lack final target confirmation with bounded recovery for missed commands.
5. Missing power readings can be treated as off; YAML boot timeout can continue.
   Add explicit unavailable/stale/ambiguous handling before relying on feedback.
6. The 30-minute gap applies to night/day cycles, not all commands. Passing time
   alone does not trigger reevaluation; neither cycle handles all restart/resume cases.
7. The old day rules can alternate at high RH and high temperature, because the
   cool-to-exhaust branch has no temperature guard.
8. No dehumidifier advisory is implemented. No current indoor/outdoor dew-point
   comparison is implemented.

Recommended implementation direction: have the bedroom card and automations use
one serialized backend controller, validate fresh power feedback, confirm the
result, and expose Auto/Manual, current phase, reason, readings, and settings.
Keep the general card reusable if desired; enforce this bedroom's HIGH-only policy.

## Humidity design constraint

Relative humidity changes with temperature. Lower outdoor RH does not necessarily
mean lower moisture content. Compare dew points derived from temperature and RH
to judge whether incoming air offers drying potential; use room RH for the user's
dryness target. Source: https://www.weather.gov/arx/why_dewpoint_vs_humidity

User confirms the bedroom door stays open and exhaust draws much drier air from
inside the house. This makes exhaust a meaningful alternative to damp outdoor
intake in this installation. An existing hallway/house temperature and RH sensor
would help quantify the benefit, but is optional. If outdoor air is drier, intake
may also dry the room. Do not promise that declining daytime outdoor RH alone
guarantees moisture removal. Preserve the requested pre-bedtime outdoor-RH guard
even if dew point is used as an additional criterion for resuming daytime intake.

For a dehumidifier advisory, the target is <=60% RH and destinations are phone
push plus Home Assistant persistent notifications. Choose and document a daytime
persistence interval before implementation. Consider failure to make progress
while exhausting house air, not just outdoor humidity. Avoid repeated alerts and
do not treat one RH sample as proof that bedding is dry. No overnight drying
alert policy has been agreed; do not create nuisance sleep-time notifications.

The <=70 F bedtime goal can conflict with holding exhaust until the TV trigger:
the fan may not have enough cooling time before 9 p.m. Do not promise that target
is guaranteed or silently introduce earlier damp-air intake. Use observed cooling
rate and TV-trigger timing to determine whether further policy adjustment is needed.

## Information still needed

1. Confirmation that the listed entity IDs still match. Home Assistant version is
   recorded above; phone notification uses the user-requested `notify.insert_here`
   placeholder and does not require further clarification.
2. Optional existing house/hallway temperature and humidity sensor IDs; short
   histories of indoor/outdoor conditions and plug watts will help tuning.
3. Remaining tuning choices: 73 vs 75 F daytime limit, alert persistence, switch
   hysteresis/dwell, and whether temperature may override the evening exhaust guard.
   Do not invent user approval for a conflict-resolution rule.
4. Whether settings should be editable on-card or just visible. Viewing settings
   and manual control are requested; implementing a full settings editor is optional.

## Next work in order

1. Use the confirmed policy and airflow facts above; collect installation IDs and
   settle the remaining tuning choices. Do not re-ask answered questions.
2. Validate physical fan states, power-on behavior, sensor latency, and IR delay
   using controlled commands before enabling unattended automation.
3. Correct controller reliability, override handling, and HIGH enforcement; implement
   the updated overnight/morning/day rules and dashboard controls.
4. Keep setup-page generated YAML, package, README, and context consistent. Test
   missed IR, stale readings, restarts, manual overrides and schedule boundaries.
5. Observe at least an overnight/daytime cycle and tune from actual temperature
   and moisture trends; add the agreed dehumidifier advisory.
6. Configure fan two after the first fan is validated. Release inspection found
   an older published tag `V0.1.0` titled "v1.0.0 - Bedroom Fan Automation";
   the title and tag differ. A release of the current code does not establish
   hardware validation or implementation of the requirements in this handoff.

Preserve plain editable YAML; prior context rejected blueprints and assumed-state
helpers. Reusing a helper for desired policy is distinct from assuming physical
fan state. Do not claim deployment, release, push, or physical testing until done.
