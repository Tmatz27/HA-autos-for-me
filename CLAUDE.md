# Repository maintenance

This repository contains a generic Home Assistant window-fan card and configurable example packages.

- Edit `den_controller.py` for den changes; edit `build.py` and `templates/` for bedroom changes, then regenerate `packages/` and `examples/`.
- Edit `dehumidifier_controller.py` for the shared device; only its automation may write dehumidifier settings. Run `python tests/test_dehumidifier.py`.
- Edit the card in `dist/window-fan-card.js`.
- Run `python tests/test_control.py` and `node tests/card.test.cjs` before releasing.
- Preserve independent mode/speed cycles, shared observed state, confirmed feedback, serialized requests and persistent deadlines.
- Bedroom climate policy is three rules in `templates/policy.jinja`: exhaust above a humidity limit, cool below a humidity limit when warm, otherwise hold the running mode. Preserve the gap between the two humidity limits, the hold-current-mode default and the minimum mode interval. Cooling raises room humidity by a couple of points, so any single threshold makes Cool and Exhaust trigger each other every evaluation.
- Den has its own comfort-cooling policy with dynamic humidity restart limits and a latched heat override and measured-range controller. Preserve the two-hour manual hold, fault latch, independent driver, overlap handling and verified startup reference. Do not apply den calibration or policy changes to the bedroom.
- Keep public examples generic. Do not commit household mappings, locations, original pasted configurations or private screenshots.
- Upgrade instructions and release notes must describe the actual generated policies and migration requirements.
