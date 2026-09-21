# Repository maintenance

This repository contains a generic Home Assistant window-fan card and configurable example packages.

- Edit `build.py` and `templates/` for controller changes, then regenerate `packages/` and `examples/`.
- Edit the card in `dist/window-fan-card.js`.
- Run `python tests/test_control.py` and `node tests/card.test.cjs` before releasing.
- Preserve independent mode/speed cycles, shared observed state, confirmed feedback, serialized requests and persistent deadlines.
- Keep exactly one phase owning the bedroom fan. Preserve the humidity deadband, the hold-current-mode default and the minimum mode interval: cooling raises room humidity, so any single-threshold rule makes Cool and Exhaust trigger each other every evaluation.
- Keep public examples generic. Do not commit household mappings, locations, original pasted configurations or private screenshots.
- Upgrade instructions and release notes must describe the actual generated policies and migration requirements.
