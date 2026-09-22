# Configuration and behavior

All values below are configurable example settings. Temperatures are Fahrenheit; room sensors reporting Celsius are converted automatically. The schedule follows Home Assistant's configured local time.

## Climate policy

Both rooms run the same three rules, in this order. `cfg` holds the three
numbers; there is nothing else to tune.

| Order | Condition | Action |
|---|---|---|
| 1 | Room RH at or above `exhaust_above` (65%) | **Exhaust** - get the moisture out, whatever the temperature |
| 2 | Room RH at or below `cool_below` (62%) **and** temp above `cool_above` (72F) | **Cool** - bring the temperature down |
| 3 | Anything else | **Hold** whatever is already running |

Rule 3 is what keeps the fan settled, and it is the reason for the gap between
62% and 65%. Cool draws outdoor air and raises room humidity by a couple of
points on its own, so with one threshold Cool pushed humidity over the line,
Exhaust pulled it back under, and each triggered the other every evaluation.
Inside the band nothing is requested, and the mode defaults to what is already
running rather than to a fixed mode.

A mode change is also held for at least `minimum_mode_seconds` (20 minutes).
The fan beeps on every press. Manual selections, sleep transitions, and
correcting a fan that is not where it was last told to be are not delayed.

Invalid or stale room readings fall back to Exhaust.

## Bedroom sleep lock

The bedroom adds the one override. Nothing else differs between the rooms.

| Condition | Action |
|---|---|
| TV goes from active to off/standby/unavailable during 22:00-06:00 | Cool/High until morning |
| Manual Cool selected during the window | Cool/High until morning |
| The window opens at 22:00 with the TV already off | Cool/High until morning |
| Morning, or the window closes | Release; the three rules resume |

While the lock is held the fan does not change mode at all, regardless of
humidity or temperature. That is deliberate: no beeping while asleep.

Outdoor readings are not used for control in either room. Exhaust only dries
the room when the replacement air is drier, which depends on the airflow path
through the house rather than on outdoor humidity at the window, so comparing
the two was a heuristic that mostly produced mode changes. Room limits are
control targets, not guarantees.

## Calibration

Managed mode uses **one decoder**, shared between the card and controller. It classifies ascending power bands in this order:

`Off → Exhaust Low → Exhaust Medium → Exhaust High → Circulate Low → Circulate Medium → Circulate High → Cool Low → Cool Medium → Cool High`

The sample boundary values are `10, 32, 34.5, 37, 41, 44, 46, 48, 50` watts. Each boundary is exclusive for the lower band. Cool High is the final open-ended band. Measure each mode/speed and confirm that the ordering and separation fit the fan. This decoder is unsuitable if distinct states overlap in watts or use a different ordering; adjust the decoder before using such hardware.

First run seeds `input_number.<room>_fan_watts_*` helpers from `BANDS` in the builder; subsequent restarts restore the edited helper values. Open **Calibration** in the card editor to edit the helpers. Temporarily disable the fan's automations while measuring or adjusting multiple boundaries, then re-enable them. Non-numeric or non-increasing boundaries produce Unknown and block remote presses.

The standalone card instead accepts nine measured wattages in its editor, a maximum deviation, and an Off threshold. It does not estimate Circulate from Cool/Exhaust. Supply all nine measurements before using it. Standalone remote actions should not run alongside a managed package; use the supplied managed card configurations for these packages.

## Feedback and timing

The motor cycles must be independent:

- Mode: Cool → Exhaust → Circulate → Cool.
- Speed: Low → Medium → High → Low.

The controller reads observed state before each press and waits for a fresh report confirming the expected result. Defaults allow 60 seconds for feedback and two seconds of settling. Missing or unconfirmed feedback stops further presses and displays the expected state, observed state and watts. Automatic retries wait five minutes; explicit card and bedtime requests can retry immediately. Physical-remote bedtime detection resumes after errors, with a short guard against delayed reports from the controller's own commands.

Available numeric power readings do not expire solely because their value has not been reported again (`power_max_age: 0`). This supports change-only reporting plugs. Set a positive `power_max_age` if the integration has a known regular reporting interval; an unavailable, unknown or invalid power value always blocks commands. An integration that leaves a disconnected sensor available can still expose an old starting value, so configure that integration's availability when supported. Every toggle must produce a new power-state update matching its expected result before another toggle is sent. Indoor readings expire after 15 minutes, using the most recent report. Routine evaluation occurs once per minute and on Home Assistant startup. Climate and power sensor reports do not start additional routine runs. Bedtime events and card commands remain event-driven. Brief feedback polling occurs only while a command sequence is active. Threshold decisions can therefore take up to one minute to respond. There is a 20-minute minimum interval between mode changes. Only a manual request, a sleep-lock transition, or correcting a fan that is not where it was last told to be bypasses it.

The optional learned `power_command` starts blank. An off smart plug can be turned on, but if the plug is already on and the fan itself is off, configure that learned command or start the fan physically. No boot mode is assumed. The package never sends a fan-off request.

Climate/timing settings live in `cfg` at the start of each generated controller. Configure source mappings in `build.py` and regenerate to keep all embedded references consistent. Existing helper values override the initial calibration seeds; editing `BANDS` alone does not change a previously initialized installation.


## Bedtime after installing or restarting

Sleep starts from a TV-off transition, an explicit Cool selection inside the bedtime window, or the bedtime check finding the TV already off when the window opens. An active saved Sleep lock survives restart, but an event that occurred before the new automation was installed cannot be replayed. Select Cool on the card to start Sleep in that case.

The editor shows Off plus all nine running ranges and their current wattages. Cool/High is the final open-ended range: its lower boundary is the Cool/Med upper boundary (50 W in the examples). Selecting Cool/High opens that shared boundary helper. This preserves existing calibration without introducing another independent cutoff.


## Manual card controls

All three modes and speeds are selectable. A mode button preserves the observed speed, and a speed button preserves the observed mode. The explicit selection takes priority over climate decisions for `manual_minutes` (30 by default). Each new selection starts a new deadline; routine evaluation and restart do not extend it. The card shows Manual and the remaining minutes, with **Resume Auto** to end the hold immediately. When the deadline expires, the next minute check resumes the current climate policy at High speed. Power confirmation and serialization still apply to every command.

Bedroom Cool during the bedtime window starts the existing sleep lock and chooses High when the mode button alone is used. After its manual hold expires, Auto continues Cool/High until morning. Explicit later speed changes can hold another speed temporarily. A new bedtime TV/observed-Cool event takes over an existing manual hold; the end of an active sleep lock also clears a remaining hold so the three rules resume on time.

The card and packages must be upgraded together. The new controller advertises manual-control support; older packages produce a clear upgrade message rather than silently discarding a click. The fan is never turned off by these controls.
