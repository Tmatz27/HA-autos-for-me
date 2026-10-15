# v1.7.0 — State-first den fan and room BroadLink controls

The den fan tracks persistent command history, uses one queued hardware executor, and supports manual holds and deterministic recovery without requiring unique wattage for every setting. The complete v1.6.0 den temperature/humidity policy is preserved. The retired bedroom implementation is removed; the independent shared dehumidifier is unchanged.

The room package also supports the existing **Den LED Strip** switch. Configure `led_device`, `led_on_command` and `led_off_command` privately. LED commands share the transmitter queue and do not change fan state, faults or manual holds. Existing switch name and unique ID are preserved.

## Install with HACS

1. Open this repository in HACS and update/redownload **v1.7.0**. The `window-fan-card.js` release asset is the HACS frontend file. Keep one dashboard resource for this card and hard-refresh afterward. The browser console should show `Window Fan Card 1.7.0`.
2. Replace the existing den YAML package with your complete privately customized replacement. **HACS updates the card; it does not install or migrate YAML packages.** The public example ZIP contains generic mappings, not household configuration. Use `examples/room-config.example.json` with the generator for other installations.
3. If the LED switch was temporarily installed as a separate package, remove that extra definition when using the combined room package. Keep only one definition of the LED switch, one den package and one den control automation. Leave the shared dehumidifier package unchanged.
4. Remove the retired bedroom package/automations if present. Run Home Assistant's configuration check, restart, confirm the physical fan setting and test manual controls before resuming Auto.

The release is built from the dedicated repair branch; it does not merge that branch into main or deploy to Home Assistant. See INSTALLATION.md in the example ZIP for migration and rollback.

## Validation

The release workflow runs the Python controller/policy/dehumidifier tests, real Chromium card tests, generated-file consistency and Home Assistant configuration checks using official 2024.10.4 and 2026.10.1 images before publishing. LED regressions cover exact on/off wiring, fan fault/sensor independence and serialization behind recovery. Climate regression compares 6,806 identical-input policy scenarios. Real IR delivery, sensor cadence and physical timing still require installation checks.

Assets: `window-fan-card.js` for HACS and a generic examples ZIP. No private hardware mappings or learned codes are published.
