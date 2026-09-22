# Repository maintenance

This repository contains a generic Home Assistant window-fan card and configurable example packages.

- Edit `build.py` and `templates/` for controller changes, then regenerate `packages/` and `examples/`.
- Edit the card in `dist/window-fan-card.js`.
- Run `python tests/test_control.py` and `node tests/card.test.cjs` before releasing.
- Preserve independent mode/speed cycles, shared observed state, confirmed feedback, serialized requests and persistent deadlines.
- Climate policy is three rules in one shared `templates/policy.jinja`: exhaust above a humidity limit, cool below a humidity limit when warm, otherwise hold the running mode. Preserve the gap between the two humidity limits, the hold-current-mode default and the minimum mode interval. Cooling raises room humidity by a couple of points, so any single threshold makes Cool and Exhaust trigger each other every evaluation.
- Do not reintroduce per-room mechanisms (bursts, recovery, outdoor comparisons, drying phases) without evidence from the running installation. Their interactions, not any one of them, caused the cycling this replaced.
- Keep public examples generic. Do not commit household mappings, locations, original pasted configurations or private screenshots.
- Upgrade instructions and release notes must describe the actual generated policies and migration requirements.
