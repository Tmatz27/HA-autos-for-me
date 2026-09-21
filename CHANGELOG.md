# Changelog

## 1.3.0

- Replace the bedroom's overlapping night/morning/protection flags with one explicit phase (`sleep`, `dry`, `balance`) that solely owns the fan, published as `input_select.bedroom_fan_phase`.
- Stop the fan oscillating once per minute. Cooling draws outdoor air and raises room humidity, so a single humidity threshold made Cool and Exhaust trigger each other; a 62-66% deadband now separates them and the mode defaults to whatever is already running.
- Raise the minimum interval between mode changes from 3 to 20 minutes and apply it in every phase. It was previously skipped during sleep and morning drying, which is where the worst cycling occurred.
- Start Sleep when the bedtime window opens with the TV already off. Previously that night ran the daytime policy, cycling the fan until morning.
- Give up drying after 60 minutes without a 1-point humidity improvement and manage temperature instead; re-arm if the room becomes materially wetter.
- Extend burst recovery to 20 minutes so no path can switch faster than the minimum hold.
- Add simulation tests that drive consecutive evaluations with humidity feedback and assert the fan does not oscillate.

## 1.2.3

- Fix manual selections being ignored by the den climate policy at ordinary room temperatures.
- Restore Cool, Exhaust, Circulate, Low, Medium and High controls in package mode.
- Hold explicit selections for 30 minutes, preserving the other observed axis; resume automatic High-speed control afterward.
- Add a compact hold countdown and Resume Auto action; persist hold deadlines across restarts.
- Preserve bedroom bedtime Cool/High behavior and scheduled morning handoff.
- Require matching package support for manual controls and test the actual ignored-click scenario plus all nine selections.

## 1.2.2

- Accept available numeric power from change-only reporting plugs; retain optional maximum report age and require a new matching power update after each toggle.
- Allow up to 60 seconds for command feedback; show expected state, observed state and watts on failure.
- Let explicit manual/bedtime requests retry immediately while retaining five-minute automatic retry spacing.
- Restore physical-remote bedtime detection after prior errors, while guarding delayed feedback from controller commands.
- Show Off and all nine calibration ranges with live wattages, including the shared Cool/High lower boundary.
- Label overnight drying correctly and document the bedtime trigger after installation/restart.
- Retain once-per-minute routine checks and existing climate goals.

## 1.2.1

- Replace package wiring fields with one **Fan** selector showing only discovered fan packages.
- Automatically connect controller/state/calibration and room sensors; recover unambiguous partially configured cards.
- Filter optional temperature, humidity and standalone power sensor choices.
- Remove setup instructions and calibration controls from the dashboard. Keep routine automation details hidden by default and retain real error feedback.
- Move calibration into the editor and separate standalone setup from package setup.
- Limit routine control to one check per minute plus startup; retain immediate bedtime/manual requests and active-command feedback checks.
- Add package discovery metadata and short card YAML examples. Climate thresholds and priorities are unchanged.
- Test discovery with 20,000 unrelated sensors, partial/ambiguous/missing configurations, room switching, editor focus and command routing.

Update the card and refresh the dashboard, then choose the fan in its editor. Existing v1.2.0 packages remain supported; refreshed package YAML adds automatic room-sensor discovery.

## 1.2.0

- Configure measured wattages for all nine operating states, including Circulate.
- Share package state and editable calibration with the managed card.
- Serialize card and automation requests and confirm fresh power feedback after each independent remote toggle.
- Add continuous High-speed bedroom and den examples with sleep lock, morning drying, humidity protection, cooling bursts and persistent recovery deadlines.
- Handle stale readings, command timeouts and startup without assuming motor state.
- Replace installation-specific examples and the obsolete setup generator with generic packages, a reproducible builder and current documentation.
- Add controller simulation and card regression tests.

Upgrade the card and packages together. Replace old fan automations, configure external entity IDs and learned commands, measure calibration, run Home Assistant's configuration check, restart and refresh the dashboard. See README.md.
