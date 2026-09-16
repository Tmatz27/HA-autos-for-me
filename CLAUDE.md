# Project context

Home Assistant control for a dual-motor IR window fan in the master bedroom.

## The problem

Vandenberg SFB: mild temperatures but very high humidity. The fan is the main
tool for keeping the bedroom sleepable — cool (intake) brings in cool air,
exhaust draws humidity down. The goal is to balance both automatically,
prioritizing sleeping temperature overnight and humidity during the day, so
we aren't fighting a hot, damp room at bedtime.

The hard part: the fan is driven by a Broadlink IR remote whose buttons are
**forward-only toggles with no state feedback**. There is no way to ask the
fan what mode or speed it's on.

## Hardware facts (these drive every design decision)

- **Mode button** cycles `cool → exhaust → circulate → cool`. One press gets
  cool→exhaust; getting exhaust→cool takes **two** (it steps via circulate).
- **Speed button** cycles `low → med → high → low`.
- **Powering on always lands at cool / low.**
- **The fan beeps on every press.** This is a bedroom — minimizing presses
  overnight is a real requirement, not a nicety.
- Circulate runs one motor each way. The motors are <4in apart on a 14in
  fan, so it's near-useless in practice; it only matters as a state to step
  through or recognize.

**The breakthrough:** every mode/speed combination draws a distinct,
repeatable wattage, so the smart plug reveals the true state. Measured:

| | Low | Med | High |
|---|---|---|---|
| Cool | 45 W | 48 W | 51 W |
| Exhaust | 31 W | 33 W | 36 W |

Circulate is the average of cool and exhaust at the same speed (38 / 40.5 /
43.5 W) and is derived, never measured. This removes any need to *remember*
state — it is always re-read, so the system self-corrects if someone uses the
physical remote.

## Entity IDs

| Purpose | Entity |
|---|---|
| Plug power (W) | `sensor.master_smart_plug_power` |
| Plug switch | `switch.master_fan_plug` |
| IR remote | `remote.master_remote` |
| IR device name | `Master Fan` |
| IR commands | `power_toggle`, `mode_toggle`, `speed_toggle` |
| Room temp / humidity | `sensor.master_air_quality_temperature` / `sensor.master_air_quality_humidity` |
| Outdoor humidity / temp | `sensor.aso_vandenberg_humidity` / `sensor.aso_vandenberg_temperature` |
| Bedtime trigger (TV) | `media_player.lg_webos_tv_oled65c2pua` |

The plug is a Shelly Plug US Gen4 (Matter). Note the power sensor was renamed
once already — verify it before debugging anything.

## Agreed control logic

Speed stays on **high** at all times. Every mode switch is held to a
**30-minute minimum gap** to limit beeping.

1. **Bedtime** — TV goes `unavailable` (not `off`) after 8pm → clear manual
   override, set cool/high, enter night phase. Mirrors the existing
   "Bedroom - Bedtime - TV Off Hatch Routine" pattern, which works reliably.
2. **Night** — → exhaust when temp ≤62 °F **and** humidity ≥75 %.
   → cool when temp ≥65 °F **or** humidity ≤60 %. Sleeping comfort
   outranks humidity: if the room warms up, go back to cool regardless.
3. **Morning** — outdoor humidity <75 % **or** 10am, whichever first → reset
   to cool/high, end night phase. Outdoor humidity here often doesn't break
   until late morning, so the clock is a backstop, not the main trigger.
4. **Day** — → exhaust when humidity ≥68 %. → cool when humidity ≤60 % **or**
   temp ≥75 °F.

Manual override (`input_boolean`) pauses both cycle automations so a manual
choice isn't reverted 30 minutes later, and auto-clears at bedtime so a
forgotten override can't disable humidity control overnight.

## What's in the repo

| Path | What |
|---|---|
| `dist/window-fan-card.js` | HACS Lovelace card. Self-contained — decodes wattage and sends IR itself, needs no helpers/sensor/script. Has a visual config editor. |
| `packages/window_fan_bedroom.yaml` | One drop-in file creating all helpers, the state sensor, the script and 4 automations. Only needed for the automations. |
| `docs/setup.html` | Setup page: enter entities + wattages, generates both configs, flags readings too close to distinguish. |

## Conventions and decisions already made

- **Power on/off uses the plug switch, not the IR power button.** The IR
  button is a blind toggle; the switch is deterministic.
- **Never store assumed fan state.** Always decode from wattage. An earlier
  design used `input_select` helpers to remember state — abandoned, it drifts.
- **Blueprints were tried and removed.** Too much indirection for a two-fan
  house; the user wants plain, directly editable YAML.
- **The button-card YAML version was replaced** by the custom card. Don't
  reintroduce a 300-line copy-paste card.
- Thresholds are plain literals in the automations — edit them directly
  rather than promoting them to `input_number` helpers.

## Status

Verified in a headless browser against the real measured wattages: 10/10
state decodes, 7/7 remote press sequences (including exhaust→cool taking two
presses and the off→boot→target path), and 13/13 band checks on the
generated package template.

**Not yet done:**

- **Never run against the real fan.** All verification is simulated. First
  real-hardware test is the priority — especially the 2-second inter-press
  delay, which is a guess at how fast the fan registers IR.
- `v1.0.0` release tag — tag pushes get HTTP 403 from the Claude Code web
  environment's proxy. Needs creating via the GitHub UI.
- The second fan (user has another to add) is not configured.
- User mentioned wanting to physically disable the fan's beeper by opening
  the unit — would relax the 30-minute dwell constraint significantly.
