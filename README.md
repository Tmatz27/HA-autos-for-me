# Den Window Fan Controller

A persistent state tracker, one serialized hardware executor, the unchanged v1.6.0 den climate policy, and a Lovelace card. The shared dehumidifier remains independent and unchanged.

**Version 1.7.0** is distributed as a HACS dashboard-card release. Public packages contain **generic examples**. Generate a private installation package using confirmed hardware mappings before installing.

## Operation

Mode advances **Cool → Exhaust → Circulate → Cool**. Speed advances **Low → Medium → High → Low** (`med` in service data). A mode request preserves speed; a speed request preserves mode. Normal changes keep the fan running and never cycle its plug.

Persistent helpers retain the expected state, confidence, running belief, manual deadline, policy cycle/deadline, last outcome, incomplete-command marker and automatic recovery budget. The historical `input_select.den_fan_confirmed_state` entity ID is retained for migration, but its meaning is now **expected state**. A returned BroadLink service call establishes command history; it cannot prove IR receipt. The card always displays this distinction and the supporting wattage evidence.

Overlapping readings such as 50.4 W retain a compatible expected state. Unavailable/stale wattage retains history and marks commands inferred. Fresh contradictory evidence after a press stops the remainder of the sequence. No state is silently replaced by a wattage classifier. See [controller details](docs/CONTROL.md).

Manual mode/speed selections immediately reserve a configurable hold (120 minutes by default), including while the executor finishes a safe command boundary. They work without temperature/humidity. The absolute deadline survives restart; each selection restarts it. **Resume Auto** ends it and evaluates the original climate policy immediately. After a failed/interrupted command, Resume Auto does not invent a reference: use **Confirm Physical State** or **Recover / Reinitialize**.

**Recover** serializes plug OFF → configured discharge wait and fresh stopped-power evidence → plug ON → configured wait → exactly one learned startup command → configured startup wait and fresh running-power evidence → Cool/Low → requested setting. Manual recovery starts a manual hold. Recovery does not automatically repeat. Optional automatic recovery defaults OFF and has one persistent attempt until an explicit successful physical confirmation or manual recovery re-arms it; a failed attempt survives restarts and requires operator intervention. A power toggle can be used as the startup command only when verified to start the stopped fan after a plug reset. It is never blindly resent.

## Preserved climate policy

Automatic speed remains High. Ordinary cooling starts at 70°F when the dynamic RH threshold permits; it continues toward 68°F, stops at 65% RH or a rise **greater than** eight points above the ten-minute minimum, and preserves the ten-minute Exhaust recovery interval. Dynamic restart limits remain 58% through 72°F, 60% at 74°F, 62% at 76°F and 65% at 78°F with the original interpolation. The 30-minute deadline remains a reassessment point. At 78°F, heat priority bypasses ordinary humidity/rapid-rise/recovery guards and stays latched until 75°F. At exit, the original ordinary stop/continuation decisions apply.

The original valid-input guard is retained: ordinary decisions need valid indoor temperature and humidity; heat priority may operate without humidity when temperature qualifies. Missing temperature always suspends automatic decisions. Unsupported decisions preserve the current fan and manual controls. Policy evaluation remains once per minute, on startup and on Resume Auto; expiry also wakes evaluation at the manual deadline. Sensor changes update evidence without introducing additional climate decisions.

The original `POLICY`, `HUMIDITY_LIMIT` and climate thresholds are frozen. Differential tests execute the v1.6.0 template and current template over identical scenarios and compare mode, cycle, deadline and reason. Hardware/state logic is tested separately.

## Files and installation

- `den_controller.py`: configurable den package generator and frozen climate policy.
- `build.py`: builds only the generic den example and independent shared dehumidifier.
- `dist/window-fan-card.js`: the only supported card; requires the den package. Legacy standalone IR sending has been removed to prevent competing controllers. Optional room LED on/off controls retain the existing switch identity and share the same BroadLink queue.
- `packages/`: generic public examples, not household configuration.
- `examples/den-card.yaml`: complete dashboard card configuration.
- [Installation and migration](docs/INSTALL.md): files to remove/replace, HACS/manual resource installation, first tests and rollback.
- [Configuration reference](docs/CONTROL.md): private generator settings and state/error semantics.
- [Verification report](docs/VERIFICATION.md): failures repaired, test coverage and physical validation checklist.

Use Home Assistant 2024.10 or newer. The workflow checks both the minimum supported release and a current release with Home Assistant's own configuration checker. Actual run results, not workflow presence, determine validation status.

Generate public examples with `python build.py`. Generate the private package with:

```sh
python den_controller.py --config /private/confirmed-fan.json --output /private/window_fan_den.yaml
```

Keep private JSON/output outside this repository. `--config` requires all installation mappings, confirmed timings, startup/off commands, wattage settings, hold duration and explicit automatic-recovery choice; it rejects unknown keys and changes to frozen climate parameters. Names are case sensitive. The power-off name is retained in configuration for clarity and is not used in normal changes or reset recovery. A verified single power-toggle identifier may occupy both power-command fields.

To include the room LEDs in the **same** package, supply `led_device`, `led_on_command` and `led_off_command` in private JSON. The `Den LED Strip` switch retains its name and `den_led_strip` unique ID. LED controls do not affect the fan's manual hold, fault or climate policy. Remove any separately installed duplicate LED template when installing the combined room package. See `examples/room-config.example.json` for generic configuration fields.

HACS installs/updates `window-fan-card.js`; it does not install YAML packages. Update the card through HACS and replace the private complete YAML package separately. The release is tagged from the repair branch; main is not merged by publishing a release.

Configure the shared dehumidifier separately using its existing generator. Install it once; this fan update requires no dehumidifier replacement.

## Development

Python 3.11+ and Node 20+ run the repository tests:

```sh
python -m pip install -r requirements-test.txt
python build.py
python -m unittest discover -s tests -p 'test_*.py' -v
npm install
npx playwright install chromium
node tests/card.test.cjs
```

Card tests run rendered buttons and events in Chromium, including service errors and a hung request. `FAN_TEST_BROWSER=chrome` selects installed Chrome for local testing. On supported Linux with Home Assistant installed, run `python tests/check_home_assistant.py` to validate generated package configuration using Home Assistant's schemas. Software simulation does not certify IR delivery, sensor reporting cadence or physical startup timing.
