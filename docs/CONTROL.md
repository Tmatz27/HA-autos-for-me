# Configuration and behavior

All values below are configurable example settings. Temperatures are Fahrenheit; room sensors reporting Celsius are converted automatically. The schedule follows Home Assistant's configured local time.

## Den controller in 1.5.0

The den has one serialized controller (`script.den_fan_set_state`) and one hardware writer (`script.den_fan_apply_state`). Card requests, minute checks and settled observations all use this path. Routine climate decisions run once per minute. Observation triggers recognize changes but do not run a second climate policy.

Automatic speed is always High. Start Cool at 78°F for 30 minutes; stop early at 74°F. Extend at the deadline if still above 74°F and RH ≤70%. Extended cooling stops at 74°F or RH >70%. After cooling, Exhaust runs for 15 minutes before another burst. Otherwise Exhaust runs continuously. An initial heat-relief burst can run above 70% RH; recovery still applies if the room remains hot. These are targets, not guarantees. Outside conditions do not veto cooling.

Manual card selections preserve the other axis and suspend automatic output for 120 minutes. New selections restart that deadline; normal checks and HA restarts do not. Resume Auto ends it early. A uniquely detected physical-remote change also starts a hold; overlapping readings cannot always reveal an external change.

Configure mappings in `build.py` and den settings/ranges in `den_controller.py`, then run `python build.py`. Alternatively run `python den_controller.py --config PRIVATE.json --output window_fan_den.yaml`; keep private configuration out of GitHub. All nine `ranges` entries must be supplied when overriding ranges. The public values are examples for one fan, not universal specifications.

| Setting | Example inclusive watts |
|---|---|
| Cool Low / Medium / High | 46–47 / 48–50 / 50–53 |
| Exhaust Low / Medium / High | 32–33 / 34–35 / 35–38 |
| Circulate Low / Medium / High | 39–40 / 42–43 / 44–46 |

`range_tolerance` defaults to ±0.5 W for rounded measurements. It expands each range and can increase overlap; it never resolves overlap by choosing the nearest label. Compatible confirmed history is retained. Without that history, overlapping or out-of-range readings remain Unknown. The editor shows all nine ranges. **Confirm fan setting** records a setting verified on the appliance, checks that its reading is compatible, sends no remote commands, and starts a manual hold.

After each independent toggle, a new live power update must fit the expected range, exclude the previous range, and settle for eight seconds; timeout is 60 seconds. Failed or interrupted commands latch a fault: automatic checks cannot retry repeatedly. A deliberate card request, Resume Auto, physical confirmation or a confirmed real startup can recover when a usable state is available. Deliberate retries are not permission to guess an ambiguous starting state. Unavailable power blocks commands; unavailable climate values suspend climate output. Numeric unchanged values do not expire just because the number stays the same. Configure integration availability so disconnected sensors become unavailable.

The example startup reference is Cool/Low. **Verify this on the actual model before enabling startup recovery.** A power reading below 10 W for 15 seconds marks a real off state, excluding brief transition dips. When subsequent power settles in the startup range, the controller establishes that reference and restores Auto or the unexpired manual target. It never turns the fan or plug off to synchronize. An HA restart alone is not a physical restart: state is reacquired from a distinct reading or physical confirmation. If the plug is off, it can be turned on. If the appliance is off while the plug is on, the optional learned power command must be configured or the fan started physically.

Five-minute min/mean/max history values are aggregated statistics, not extra live feedback channels. Use the live power entity for command confirmation.

### Den migration

Replace the old den package rather than adding a second copy. Disable separately copied den automations. Keep Den Fan Continuous Control disabled while replacing the package, updating the card, checking HA configuration and restarting. Existing disabled automation state may remain disabled after restart. Verify manual commands against physical indicators, then enable this one automation and use Resume Auto. Existing old calibration helpers are no longer read by the den controller. Do not replace an installation's bedroom package for this den update. Failed commands retain traces under both den scripts.

## Bedroom climate policy

The unchanged bedroom package runs these three rules, in this order. `cfg` holds the three
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

The bedroom adds this override. The den uses its separate controller described above.

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

## Bedroom and standalone calibration

Managed mode uses **one decoder**, shared between the card and controller. It classifies ascending power bands in this order:

`Off → Exhaust Low → Exhaust Medium → Exhaust High → Circulate Low → Circulate Medium → Circulate High → Cool Low → Cool Medium → Cool High`

The sample boundary values are `10, 32, 34.5, 37, 41, 44, 46, 48, 50` watts. Each boundary is exclusive for the lower band. Cool High is the final open-ended band. Measure each mode/speed and confirm that the ordering and separation fit the fan. This decoder is unsuitable if distinct states overlap in watts or use a different ordering; adjust the decoder before using such hardware.

First run seeds `input_number.<room>_fan_watts_*` helpers from `BANDS` in the builder; subsequent restarts restore the edited helper values. Open **Calibration** in the card editor to edit the helpers. Temporarily disable the fan's automations while measuring or adjusting multiple boundaries, then re-enable them. Non-numeric or non-increasing boundaries produce Unknown and block remote presses.

The standalone card instead accepts nine measured wattages in its editor, a maximum deviation, and an Off threshold. It does not estimate Circulate from Cool/Exhaust. Supply all nine measurements before using it. Standalone remote actions should not run alongside a managed package; use the supplied managed card configurations for these packages.

## Bedroom feedback and timing

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


## Bedroom manual card controls

All three modes and speeds are selectable. A mode button preserves the observed speed, and a speed button preserves the observed mode. The explicit selection takes priority over climate decisions for `manual_minutes` (30 by default). Each new selection starts a new deadline; routine evaluation and restart do not extend it. The card shows Manual and the remaining minutes, with **Resume Auto** to end the hold immediately. When the deadline expires, the next minute check resumes the current climate policy at High speed. Power confirmation and serialization still apply to every command.

Bedroom Cool during the bedtime window starts the existing sleep lock and chooses High when the mode button alone is used. After its manual hold expires, Auto continues Cool/High until morning. Explicit later speed changes can hold another speed temporarily. A new bedtime TV/observed-Cool event takes over an existing manual hold; the end of an active sleep lock also clears a remaining hold so the three rules resume on time.

The card and packages must be upgraded together. The new controller advertises manual-control support; older packages produce a clear upgrade message rather than silently discarding a click. The fan is never turned off by these controls.
