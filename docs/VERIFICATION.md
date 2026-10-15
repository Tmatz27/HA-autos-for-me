# Verification report — development branch

## Root causes in v1.6.0

1. Per-press feedback required the expected wattage band AND exclusion of the previous band. Valid overlapping Medium/High readings could never satisfy it; the driver latched a fault and erased the reference.
2. Startup explicitly discarded restored history, requiring wattage reacquisition. Ambiguous readings then could not recover a setting.
3. The power recovery branch used plug ON *instead of* then sending a learned startup command. This hardware remains stopped after electricity is restored. An empty configured power command compounded the failure.
4. Physical confirmation was rejected unless its selected setting matched the wattage band. It could not override misleading/missing feedback.
5. Manual requests shared coordinator prerequisites that reconciled/classified watts before manual intent could execute. The card also contained a separate standalone IR sender and hid physical confirmation in the editor.
6. The diagnostic's unknown climate sources prevented the policy's required ordinary inputs from evaluating. Confirmed private mappings must be generated consistently; public example IDs cannot repair an installation.

## Changes

`den_controller.py`, generated den YAML and `build.py`: persistent expected state, confidence, running belief, intent marker, outcome, recovery status and one queued executor. Manual admission reserves hold immediately; all requests and reset/confirmation use that executor. Bounded feedback keeps overlap/incomplete measurement distinct from known contradiction. Reset verifies stopped evidence, restores power, sends the learned startup command once and establishes Cool/Low before independent cyclic presses. Automatic recovery is disabled by default and has a persistent one-attempt budget if enabled.

`dist/window-fan-card.js` and card example: package-only controls, watts/climate readings, expected-state/confidence, hold/resume, visible recovery/confirmation and surfaced errors. Transport timeout clears the local busy state without retrying. No direct IR/plug output remains in the browser.

Retired bedroom package/example/template and generator/test paths are removed. Documentation and setup guide describe only supported den behavior plus explicit migration. The independent dehumidifier source and generated YAML remain unchanged.

## Validation status

Validated code commit: `ca1933165866cd719bdcb9e28e12343805a57e5e`. [Successful CI run](https://github.com/Tmatz27/HA-autos-for-me/actions/runs/38687436872).

- **52 Python tests passed**, covering generated actions, differential policy, build/mapping invariants and the unchanged dehumidifier.
- **Chromium card tests passed** locally in installed Chrome and in Linux CI.
- Generated YAML/Jinja checks and generated-file consistency passed.
- Home Assistant's own configuration checker passed using official **2024.10.4** and **2026.10.1** images, with generic complete den and shared-dehumidifier packages. The containers had network disabled and did not contact household equipment.
- The independent dehumidifier source and generated package have no diff from v1.6.0.

Initial CI setup issues (platform line endings and pip's resolution of old-release dependencies) were corrected before the successful run. No runtime or physical validation is claimed from schema checks. Installation-specific output requires separate confirmed settings and the user's full-instance configuration check.

Policy differential coverage: **6,806 identical-input comparisons** of mode, cycle, deadline and full reason, plus the original detailed climate scenarios (dynamic thresholds, ordinary cooling/termination, strict >8 rise guard, prolonged drying, heat latch/exemptions, exit and recovery). Manual hold/expiry/resume and sensor availability are separately exercised through generated actions.

Hardware coverage: all 81 state transitions, each of nine reset targets, independent axes, startup order/reference, failed startup, missed/delayed/unchanged/stale power, overlapping 50.4 W, physical confirmation including mismatches, persisted restart intent/hold, physical power loss, queue/preemption, interruption and duplicate requests, one-attempt recovery and no overlap-triggered reset. The simulator runs actual generated YAML actions; it is not Home Assistant's runtime or physical IR.

Browser coverage: rendered mode/speed buttons, nine shared states, unavailable climate, visible confirmation/recovery, manual display and Resume Auto, backend/service errors, transport timeout and absence of direct IR calls. This uses an actual browser DOM; it is not a connected Home Assistant frontend session.

## Limitations and required physical verification

- No software test proves BroadLink delivery. A missed press hidden by overlapping bands remains inferred and may require physical confirmation/recovery. At most four cyclic presses are calculated for a request; no toggle is automatically retransmitted after failure.
- Changes made with the physical remote while Home Assistant is offline can be indistinguishable from restored history when wattage overlaps. Restart downgrades confidence; confirm/recover when needed.
- Sensor report freshness depends on the integration. Fake/retained readings repeatedly re-reported as current cannot be distinguished from real measurements. Verify disconnected-sensor availability and change-only reporting behavior.
- Confirm the actual learned power identifier, OFF/plug/startup/press waits, stopped threshold and wattage bands before labeling a private package ready. Do not infer timing from a public example.
- Verify all nine physical settings, untouched-axis behavior, first manual command, hold restart/expiry, Resume Auto, unavailable climate manual control, plug OFF→ON→startup command, failed-start safe stop, and restart interruption on the user's fan. See INSTALL.md.
- Configuration schema checks cannot certify the existing household's complete YAML, resource cache or duplicate controllers. Run the installation configuration check and observe traces before enabling Auto.

No merge, release or deployment is authorized by this report.
