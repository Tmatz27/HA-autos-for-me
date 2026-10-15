# Changelog

## 1.7.0

- Replace the den wattage-led driver with persistent expected state and one queued hardware executor.
- Preserve the complete v1.6.0 den climate policy and climate constants.
- Add serialized deterministic recovery, independent manual holds, visible physical confirmation and actionable interruption errors.
- Remove the retired bedroom implementation, generator, examples, documentation and tests. See INSTALL.md for migration from an existing installation.
- Remove standalone dashboard IR sending; the card requires the den package.
- Restore optional LED controls inside the same room package, preserving switch identity and sharing the fan transmitter queue.
- Publish the versioned card asset and generic example bundle for HACS after validation.
- Preserve the independent shared dehumidifier source and generated package unchanged.
- Add policy differential tests, generated-action simulations, real-browser card tests and Home Assistant configuration-check CI.

Releases do not deploy to Home Assistant automatically. Earlier release history remains available in Git tags.
