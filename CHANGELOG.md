# Changelog

## 1.2.0

- Configure measured wattages for all nine operating states, including Circulate.
- Share package state and editable calibration with the managed card.
- Serialize card and automation requests and confirm fresh power feedback after each independent remote toggle.
- Add continuous High-speed bedroom and den examples with sleep lock, morning drying, humidity protection, cooling bursts and persistent recovery deadlines.
- Handle stale readings, command timeouts and startup without assuming motor state.
- Replace installation-specific examples and the obsolete setup generator with generic packages, a reproducible builder and current documentation.
- Add controller simulation and card regression tests.

Upgrade the card and packages together. Replace old fan automations, configure external entity IDs and learned commands, measure calibration, run Home Assistant's configuration check, restart and refresh the dashboard. See README.md.
