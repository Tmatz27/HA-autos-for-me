# Configuration and behavior

All values below are configurable example settings. Temperatures are Fahrenheit; room sensors reporting Celsius are converted automatically. The schedule follows Home Assistant's configured local time.

## Bedroom example

Exactly one **phase** owns the fan at any moment, published as
`input_select.bedroom_fan_phase`. Phases never overlap, so two rules cannot pull
the fan in opposite directions:

| Phase | Owns the fan when | Behavior |
|---|---|---|
| `sleep` | A bedtime signal latched during 22:00–06:00 | Cool/High until morning, with no mode changes at all |
| `dry` | From the morning boundary until humidity reaches target | Exhaust, interrupted only by temperature-ceiling bursts |
| `balance` | The rest of the day | Humidity held inside a deadband; cooling when it is safe |

| Condition | Action |
|---|---|
| TV goes from active to off/standby/unavailable, or manual Cool, during 22:00–06:00 | `sleep`: Cool/High until 06:00, regardless of humidity |
| TV already off when the 22:00 window opens | `sleep` starts at 22:00 |
| Morning boundary passes | `dry`: Exhaust until RH ≤60%, or RH ≤62% when temperature >73°F |
| Drying shows no 1-point improvement for 60 minutes | Give up drying; hand to `balance` to manage temperature |
| Room becomes 5 points wetter than its best reading | Re-arm drying; this is no longer the situation it gave up on |
| `balance`, RH ≥66% | Exhaust |
| `balance`, RH ≤62% with ≥73°F and no protection | Cool |
| `balance`, RH between 62% and 66% | **Hold whatever is already running** |
| Outdoor RH exceeds indoor RH by ≥15 points | Enter protection; release below 8 points. Suppresses comfort cooling only |
| Room >75°F in any working phase | 30-minute cooling burst; stop early at ≤73°F |
| First burst expires with room >73°F and RH <64% | One 30-minute extension; ends early at RH ≥64% or ≤73°F |
| Burst/extension ends | Exhaust recovery for at least 20 minutes |

The 62–66% deadband is what keeps the fan settled. Cooling draws outdoor air and
therefore raises room humidity, so with a single threshold the fan cooled until
it crossed the line, exhausted until it crossed back, and repeated every minute.
Nothing inside the band requests a change, and the mode now defaults to whatever
is already running rather than to a fixed mode.

Sleep overrides everything else. With Sleep inactive, invalid or stale indoor
readings cause Exhaust. Missing outdoor humidity enables protection while still
permitting heat-relief bursts. Protection suppresses comfort cooling but never
the temperature ceiling.

The 5-point re-arm margin (`rearm_margin`) is deliberately wider than the 2-3
points that switching to Cool adds on its own. A narrower margin would let the
fan's own intake re-arm a drying run that has already been shown not to work.

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

First run seeds `input_number.<room>_fan_watts_*` helpers from `BANDS` in the builder; subsequent restarts restore the edited helper values. Open **Calibration** in the card editor to edit the helpers. Temporarily disable the fan's automations while measuring or adjusting multiple boundaries, then re-enable them. Non-numeric or non-increasing boundaries produce Unknown and block remote presses.

The standalone card instead accepts nine measured wattages in its editor, a maximum deviation, and an Off threshold. It does not estimate Circulate from Cool/Exhaust. Supply all nine measurements before using it. Standalone remote actions should not run alongside a managed package; use the supplied managed card configurations for these packages.

## Feedback and timing

The motor cycles must be independent:

- Mode: Cool → Exhaust → Circulate → Cool.
- Speed: Low → Medium → High → Low.

The controller reads observed state before each press and waits for a fresh report confirming the expected result. Defaults allow 60 seconds for feedback and two seconds of settling. Missing or unconfirmed feedback stops further presses and displays the expected state, observed state and watts. Automatic retries wait five minutes; explicit card and bedtime requests can retry immediately. Physical-remote bedtime detection resumes after errors, with a short guard against delayed reports from the controller's own commands.

Available numeric power readings do not expire solely because their value has not been reported again (`power_max_age: 0`). This supports change-only reporting plugs. Set a positive `power_max_age` if the integration has a known regular reporting interval; an unavailable, unknown or invalid power value always blocks commands. An integration that leaves a disconnected sensor available can still expose an old starting value, so configure that integration's availability when supported. Every toggle must produce a new power-state update matching its expected result before another toggle is sent. Indoor readings still expire after 15 minutes and outdoor humidity after two hours, using the most recent report. Routine evaluation occurs once per minute and on Home Assistant startup. Climate and power sensor reports do not start additional routine runs. Bedtime events and card commands remain event-driven. Brief feedback polling occurs only while a command sequence is active. Room-threshold and recovery decisions can therefore take up to one minute to respond. There is a 20-minute minimum interval between mode changes. It applies in every phase. Only a phase change, a burst/recovery transition, or a manual request bypasses it, and those are each bounded by their own timers.

The optional learned `power_command` starts blank. An off smart plug can be turned on, but if the plug is already on and the fan itself is off, configure that learned command or start the fan physically. No boot mode is assumed. The package never sends a fan-off request.

Climate/timing settings live in `cfg` at the start of each generated controller. Configure source mappings in `build.py` and regenerate to keep all embedded references consistent. Existing helper values override the initial calibration seeds; editing `BANDS` alone does not change a previously initialized installation.


## Bedtime after installing or restarting

Sleep starts from a TV-off transition, an explicit Cool selection inside the bedtime window, or the bedtime check finding the TV already off when the window opens. An active saved Sleep lock survives restart, but an event that occurred before the new automation was installed cannot be replayed. Select Cool on the card to start Sleep in that case. Overnight drying while waiting for the bedtime trigger is labeled Night drying, not Morning drying.

The editor shows Off plus all nine running ranges and their current wattages. Cool/High is the final open-ended range: its lower boundary is the Cool/Med upper boundary (50 W in the examples). Selecting Cool/High opens that shared boundary helper. This preserves existing calibration without introducing another independent cutoff.


## Manual card controls

All three modes and speeds are selectable. A mode button preserves the observed speed, and a speed button preserves the observed mode. The explicit selection takes priority over climate decisions for `manual_minutes` (30 by default). Each new selection starts a new deadline; routine evaluation and restart do not extend it. The card shows Manual and the remaining minutes, with **Resume Auto** to end the hold immediately. When the deadline expires, the next minute check resumes the current climate policy at High speed. Power confirmation and serialization still apply to every command.

Bedroom Cool during the bedtime window starts the existing sleep lock and chooses High when the mode button alone is used. After its manual hold expires, Auto continues Cool/High until morning. Explicit later speed changes can hold another speed temporarily. A new bedtime TV/observed-Cool event takes over an existing manual hold; the end of an active sleep lock also clears a remaining hold so morning drying starts on time.

The card and packages must be upgraded together. The new controller advertises manual-control support; older packages produce a clear upgrade message rather than silently discarding a click. The fan is never turned off by these controls.
