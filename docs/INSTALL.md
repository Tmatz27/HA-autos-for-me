# Installation, migration and rollback

Do not install the public generic example unchanged. Use the privately generated package after entity names, learned identifiers, calibration and timing have been confirmed. The v1.7.0 HACS release updates the card; the customized YAML package must be replaced separately. Publishing a release does not merge main or deploy to your instance.

## 1. Back up and stop duplicate control

1. Download a Home Assistant backup. Save the currently installed den/bedroom packages, any separately copied fan automations/scripts, dashboard YAML and JavaScript resource URLs outside the active packages directory.
2. Disable the existing den and bedroom fan automations before changing package files. Disable any copied legacy fan automation, script, Node-RED flow or dashboard action that sends fan mode/speed commands. Do not disable the shared dehumidifier automation.
3. Remove `window_fan_bedroom.yaml` from the loaded packages directory. Also remove any separately copied bedroom template/statistics sensors, bedtime/TV automations, wattage helpers, manual/sleep-lock scripts and bedroom dashboard examples. Removing the file only removes YAML-defined entities after reload/restart; UI-created duplicates must be disabled/deleted separately. Retire old bedroom cards and any direct remote dashboard controls.
4. Remove the OLD den package file; install exactly one replacement `window_fan_den.yaml`. Do not add the replacement under a second filename. Keep `shared_dehumidifier.yaml` as installed; its behavior and source are unchanged.
5. The new den package retains the continuous-control automation ID and important state/deadline helper IDs. Old `den_fan_apply_state`, `den_fan_boot_pending`, and `den_fan_command_guard_until` are retired. After restart they must not be active from another package or UI copy. Delete orphaned entities from the registry only after confirming which files own them. Do not delete persistent history helpers during a normal upgrade.
6. The combined room package can retain the old Den LED Strip switch using private `led_device`, `led_on_command` and `led_off_command` settings. Its original name and unique ID are preserved. If you temporarily installed `existing_den_led.yaml` separately, remove that extra definition when installing the combined package. Keep one LED switch definition. Preserve any other unrelated controls that are not present in the replacement before removing their old definitions.

## 2. Put the replacement files in place

Enable packages once in `/config/configuration.yaml` (merge into an existing `homeassistant:` section):

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Copy the private complete file to `/config/packages/window_fan_den.yaml`. Check that every occurrence of the external hardware entities matches the confirmed private config; the generator propagates them into policy inputs, sampling/statistics, display links, triggers and actions. Never edit only the embedded `cfg` and leave template references unchanged.

Open the repository in HACS and update/redownload **v1.7.0**. Keep the actual HACS JavaScript-module resource URL shown by your installation and hard-refresh the browser. If you temporarily added a manual `/local/window-fan-card.js` resource, remove that duplicate resource when returning to the HACS copy. Two URLs defining the same custom element cannot coexist. The filename in `hacs.json` and release asset remains `window-fan-card.js`.

HACS updates the dashboard card; it does **not** install, merge or replace the YAML room package. Copy your privately customized combined YAML as described above. The public release examples contain generic mappings.

For manual card installation instead, copy the supplied card to `/config/www/window-fan-card.js`, keep just one resource, and use:

```yaml
url: /local/window-fan-card.js?v=1.7.0
type: module
```

Increment the URL version when replacing a manual copy so an old cached file is not reused. For HACS, use its managed resource and update flow; do not guess or create a second HACS folder path.

Complete dashboard card:

```yaml
type: custom:window-fan-card
name: Den Window Fan
fan_package: sensor.den_fan_state
setup_mode: package
```

The package links power, temperature, humidity and status entities automatically. Remove old explicit card mappings that would obscure the generated links. Legacy standalone cards must be replaced by this package card.

## 3. Check configuration and restart safely

1. Run **Developer tools → YAML → Check configuration** (called **Tools** in some newer versions), or `ha core check` on Home Assistant OS. Resolve every configuration error before restarting. The repository's syntax/schema checks do not certify your whole installation.
2. Restart Home Assistant once. Reloading just automations does not load all new helpers/template/statistics entities or remove all retired ones.
3. Hard-refresh the dashboard or fully close/reopen the mobile frontend. If necessary clear its frontend cache. The browser console should show `Window Fan Card 1.7.0`; use the Network panel to verify the new resource URL/content.
4. Inspect **States**. Expect `sensor.den_fan_state`, `sensor.den_fan_power_candidates`, `sensor.den_fan_control_status`, `sensor.den_fan_humidity_sample`, `sensor.den_fan_humidity_min_10m`, `script.den_fan_set_state`, `script.den_fan_executor`, and `script.den_fan_confirm_state`. Expect the configured real power/plug/remote/climate entities to exist with appropriate readings/units.
5. Check helpers for expected state, confidence, running, command fault/in-progress, Auto recovery used, requested/manual mode/speed, recovery, policy cycle, manual/cycle deadlines and last-command time, reason/error/outcome. Template entity IDs must not have an unexpected `_2` suffix. Resolve duplicate registry entries and old definitions before proceeding.
6. Keep the den automatic automation disabled for first physical checks. Manual card requests work while it is disabled. A fresh installation starts unknown; a migrated reference may be restored as inferred. Verify it physically before toggling.

## 4. First manual and recovery checks

1. Read the real fan's lights. Open **Confirm Physical State**, choose BOTH axes and confirm. No IR or plug action should occur. The selected state must appear exactly; a wattage discrepancy is displayed rather than substituted.
2. Press one mode button and watch for the correct number of beeps/steps. Verify the untouched speed stayed unchanged. Then press a speed button and verify mode stayed unchanged. Check that the card reports inferred expected state after a command, not independently proven delivery. Each press begins/renews the configured manual hold.
3. Check all nine combinations. Record wattage bands after settling; overlap is allowed. Confirm remote delivery and minimum button delay on the actual fan.
4. Use **Recover / Reinitialize**. Verify plug OFF for the confirmed discharge interval, zero power, plug ON while the motor remains stopped, exactly one startup command, Cool/Low startup, then the correct independent toggles to the saved requested destination. Confirm the reset/status changes complete and there is no repeated power cycling.
5. If Power On fails or fresh OFF/running evidence is absent, the sequence must stop with a specific error. Inspect hardware, command names and reporting cadence. Do not repeatedly click Recover. A known physical setting can be confirmed as the fallback.
6. Disconnect/restore a room sensor and verify manual buttons remain usable. Verify an ambiguous 50.4 W reading compatible with history does not erase state or reset the plug.

## 5. Automatic behavior and restart

Enable exactly one **Den Fan – Continuous Control** automation, then press Resume Auto. The manual deadline clears immediately and the unchanged policy reevaluates at High. If climate inputs do not support a decision, the reason says climate unavailable and the fan keeps its current setting; the original heat-priority missing-humidity exception remains intact. Do not manufacture sensor states in a live installation to test heat behavior; use software scenarios or normal observed conditions.

Check ordinary humidity/temperature decisions and the displayed policy reason. Begin a short privately configured hold if an expiry test is needed, confirm that expiry resumes Auto, then restore the desired duration. Restart during an active hold and confirm that the original absolute deadline remains unchanged. If a restart/cancellation interrupts a toggle or reset, controls must require confirmation/recovery; an in-progress helper must never leave the browser indefinitely busy.

Observe real sensor availability and report cadence. A service success cannot prove IR receipt; overlapping power can hide a missed step. If physical lights disagree with the expected state, stop commands and confirm/recover.

## 6. Rollback

Disable the new den automation and stop the executor before changing files. Move the replacement package out of the active directory, restore the backed-up old den package/card resource and any separately moved unrelated switches, then check configuration and restart. Keep the shared dehumidifier untouched. Never enable old and new controllers together. Hard-refresh the browser so it loads the matching old card. The old driver has the known overlap/recovery failures; restore a physical reference and inspect its fault before enabling automatic control. Restore the retired bedroom package only if deliberately reverting that removal, with all its associated entities/controllers reviewed for duplicates.

Official references: [packages](https://www.home-assistant.io/docs/configuration/packages/), [dashboard resources](https://www.home-assistant.io/dashboards/dashboards/#resources), [BroadLink learned commands](https://www.home-assistant.io/integrations/broadlink/).
