# Configuration and behavior

All values below are configurable example settings. Temperatures are Fahrenheit; room sensors reporting Celsius are converted automatically. The schedule follows Home Assistant's configured local time.

## Bedroom example

| Condition | Action |
|---|---|
| TV goes from active to off/standby/unavailable, or manual Cool, during 22:00–06:00 | Cool/High sleep lock until 06:00, regardless of humidity |
| TV already off when the window begins | Wait for manual Cool |
| Morning | Exhaust drying until RH ≤60%, or RH ≤62% when temperature >73°F |
| Normal daytime | Begin Cool at ≥73°F and RH ≤62%; retain Cool below 73°F while humidity stays acceptable |
| Outdoor RH exceeds indoor RH by ≥15 percentage points | Enter protection; release when the gap drops below 8 points |
| Drying/protection or indoor RH >62%, and room >75°F | Permit a 30-minute cooling burst; stop early at ≤73°F |
| First burst expires with room >73°F and RH <64% | Permit one additional 30-minute extension; end early at RH ≥64% or temperature ≤73°F |
| Burst/extension ends | Exhaust recovery for at least 15 minutes |

Sleep overrides daytime rules. With Sleep inactive, invalid or stale indoor readings cause Exhaust. Missing outdoor humidity enables protection while still permitting heat-relief bursts. Protection applies whenever Sleep is inactive, not only in the evening.

Manual Cool on the managed card is explicit bedtime intent, even when the fan is already cooling. A physical remote requires an observable settled transition into Cool; a press with no state change cannot be inferred from watts. Speed-only changes do not start Sleep. A TV connection loss after an active state counts as off in this example; remove `unavailable` from that trigger if inappropriate for the integration.

## Den example

| Condition | Action |
|---|---|
| Below 78°F without an active burst | Exhaust/High |
| Room ≥78°F | Start a 30-minute cooling burst even when humidity is high |
| Room reaches ≤74°F | End cooling early |
| Burst expires, room >74°F and RH ≤70% | Keep cooling; evaluate every minute and renew the deadline every 30 minutes |
| At expiry RH >70%, or RH rises >70% during extended cooling | Exhaust recovery for at least 15 minutes |

Indoor humidity above the target is allowed during the initial heat-relief burst. Room limits are control targets, not guaranteed environmental limits.

## Calibration

Managed mode uses **one decoder**, shared between the card and controller. It classifies ascending power bands in this order:

`Off → Exhaust Low → Exhaust Medium → Exhaust High → Circulate Low → Circulate Medium → Circulate High → Cool Low → Cool Medium → Cool High`

The sample boundary values are `10, 32, 34.5, 37, 41, 44, 46, 48, 50` watts. Each boundary is exclusive for the lower band. Cool High is the final open-ended band. Measure each mode/speed and confirm that the ordering and separation fit the fan. This decoder is unsuitable if distinct states overlap in watts or use a different ordering; adjust the decoder before using such hardware.

First run seeds `input_number.<room>_fan_watts_*` helpers from `BANDS` in the builder; subsequent restarts restore the edited helper values. Open **Shared wattage calibration** on the card to edit the helpers. Temporarily disable the fan's automations while measuring or adjusting multiple boundaries, then re-enable them. Non-numeric or non-increasing boundaries produce Unknown and block remote presses.

The standalone card instead accepts nine measured wattages in its editor, a maximum deviation, and an Off threshold. It does not estimate Circulate from Cool/Exhaust. Supply all nine measurements before using it. Standalone remote actions should not run alongside a managed package; use the supplied managed card configurations for these packages.

## Feedback and timing

The motor cycles must be independent:

- Mode: Cool → Exhaust → Circulate → Cool.
- Speed: Low → Medium → High → Low.

The controller reads observed state before each press and waits for a fresh report confirming the expected result. Defaults allow 30 seconds for feedback and two seconds of settling. Missing, stale or unconfirmed feedback stops further presses and displays the error. Automatic retries wait five minutes.

Power readings must be no older than 120 seconds; indoor readings 15 minutes; outdoor humidity two hours. Freshness uses the most recent report, including unchanged values. Match these limits to device reporting intervals. Evaluation occurs each minute, on sensor changes, on settled state changes and on Home Assistant startup. There is a three-minute minimum interval for ordinary mode changes; bedtime, morning and burst/recovery transitions bypass it.

The optional learned `power_command` starts blank. An off smart plug can be turned on, but if the plug is already on and the fan itself is off, configure that learned command or start the fan physically. No boot mode is assumed. The package never sends a fan-off request.

Climate/timing settings live in `cfg` at the start of each generated controller. Configure source mappings in `build.py` and regenerate to keep all embedded references consistent. Existing helper values override the initial calibration seeds; editing `BANDS` alone does not change a previously initialized installation.
