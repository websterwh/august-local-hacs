# August Local: Implementation Scope

This replaces an earlier summary that incorrectly described guessed factory enrollment as a working, production-ready feature.

## Current architecture

- `account.py`: account authentication/verification and discovery of already installed offline keys. Account passwords and tokens are temporary in August Local.
- `config_flow.py`: one account-assisted import path, installed-key validation, and delegation to the official Yale Access Bluetooth integration. Existing installations can reconnect their same lock through options.
- `protocol.py`, `manager.py`, `panel.py`: local PIN operations and per-HA-user management of explicitly owned/reserved slots. A compatible, already paired keypad is required. Local records are not a complete inventory of the lock's PINs.
- `auto_lock.py`, `nearby.py`, `binary_sensor.py`: lock-native timer operations and HA-side proximity/arrival support. These implementations do not establish that all app features work on every firmware.
- `commissioning.py`: experimental server-assisted authentication adapter, not a registration or setup implementation.
- `enrollment.py`: unverified experimental code, not exposed by the wizard. Do not use it on an installed lock.

## Not implemented as full setup

Factory registration, installing a new owner key, calibration, keypad pairing, and interrupted-commissioning recovery still require protocol work and end-to-end verification. Arbitrary advertisement slices are not verified handshake nonces. GATT write acceptance and successful local AES encryption do not establish that a lock authenticated or applied a command.

Bluetooth operation uses an installed key and slot; it does not prove that the lock's Wi-Fi or the official August integration stops contacting cloud services. HA configuration and PIN storage must be treated as sensitive; do not assume configuration is encrypted at rest.

## Multiple accounts and resets

A separate owner account may help key availability or isolate HA credentials from a phone's key rotation. Accumulating keys is not established to improve auto-unlock, PIN capacity, scheduling, or pairing. BLE operations should remain serialized.

No permanence through factory reset, ownership removal, or account deletion has been established. Preserve the account association and working credentials. See [BOOTSTRAP_ENROLLMENT.md](BOOTSTRAP_ENROLLMENT.md) for evidence and the separately approved reset experiment.

## Installation and verification

Install from the existing [HACS custom repository](https://github.com/websterwh/august-local-hacs), using `custom_components/august_local`. This is not a public HACS catalog submission.

See [SETUP.md](SETUP.md) for the wizard, [LOCAL_TESTING.md](LOCAL_TESTING.md) for safe test scope, and [TEST_RESULTS.md](TEST_RESULTS.md) for the limitations of earlier test claims. No hardware readiness claim follows merely from the presence of these components.
