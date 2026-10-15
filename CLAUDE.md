# Repository maintenance

- Edit `den_controller.py` for the den package. Its POLICY, HUMIDITY_LIMIT and climate constants are frozen from v1.6.0. Hardware/state tracking may change; climate decisions may not.
- Edit the dashboard in `dist/window-fan-card.js`. All controls must call the request script; no direct fan IR or plug commands in the browser.
- Only `script.den_fan_executor` may drive fan hardware. Keep its queue, independent cycles, persistent intent markers and deadlines.
- Run `python build.py`, all Python tests, and the Playwright card tests. Home Assistant's own configuration checker runs in Linux CI; distinguish actual pass results from unexecuted checks.
- The shared dehumidifier remains independent. Avoid changes to its source or generated YAML; run its existing regression tests.
- Do not restore retired fan implementations or obsolete templates into the generator.
- Public examples must stay generic. Never commit household mappings, learned names/codes, private configuration, screenshots or customized output.
- Document migration, state uncertainty and real-hardware checks accurately. Do not label an unconfirmed example ready to install.
