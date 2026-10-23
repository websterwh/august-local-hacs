# August Local: Local Testing

## Safe software checks

Run the synthetic setup regressions without connecting to a lock:

```bash
python -m unittest discover -s tests -p 'test_setup_regressions.py' -v
python -m unittest discover -s tests -p 'test_inventory.py' -v
python -m unittest discover -s tests -p 'test_pin_manager.py' -v
python -m unittest discover -s tests -p 'test_initialization_adapter.py' -v
python -m unittest discover -s tests -p 'test_keypad_protocol.py' -v
python -m unittest discover -s tests -p 'test_nearby.py' -v
node --check custom_components/august_local/panel.js
node tests/test_panel.js
```

These checks use mocked transport/HA behavior. They do not establish real authentication, registration, key installation, calibration, keypad pairing, or motor operation. Use an isolated Python environment with the declared dependencies; do not downgrade the host's cryptography package to accommodate capture tooling.

`tests/test_all_components.py` and `tests/debug_lock_connectivity.py` access Bluetooth hardware. The former also contains experimental writes. They are **not** safe default software verification commands and are not evidence of successful enrollment. See [TEST_RESULTS.md](TEST_RESULTS.md).

## Account-assisted setup checks

The wizard imports an existing, installed owner key via the official HA August integration. The official integration must be loaded and signed in before the August Local wizard can proceed. Key validation is read-only and does not intentionally move the deadbolt.

For an explicitly authorized HA acceptance test, verify:

- Account errors direct to the official August integration and do not expose or log credentials.
- Account locks without installed offline keys cannot complete setup.
- Unreachable or rejected Bluetooth credentials cannot create an integration entry.
- Successful validation delegates the selected key/slot to Yale Access Bluetooth.
- Reconnecting an existing installation to another lock is rejected before Bluetooth validation.
- PIN records, slots, keys and unrelated account locks are not changed by failed setup.

Do not run setup concurrently with another BLE client. Direct desktop Bluetooth is not a substitute for testing HA's proxy path.

## Arrival-unlock verification

Check rejected scenarios before a live unlock: missing trigger context, unknown/unavailable origin, insufficient actual time away, a later arrival reusing an older wait, proximity off or stale, future/pre-arrival samples, and source/proximity changes after waiting. Rendering isolated fixtures through HA's template API does not require changing real entity states or invoking lock actions.

For an explicitly authorized controlled unlock, keep actual Bluetooth proximity and closed-door safety checks. An isolated temporary tracker avoids changing the real phone's GPS and triggering unrelated home/away automations. Preserve the configured away duration, allow only one test arrival, and remove the temporary automation/tracker and restore the production automation afterwards. Report simulated arrival separately from a real departure/return test; it does not establish background GPS reliability.

## Hardware operations require separate scope

**Advanced PIN setup → Read slot occupancy** is read-only and never allocates a slot or sends a test PIN. Compare known working slots before drawing conclusions about read support. Sanitized diagnostics include a fixed failure code, slot, result/length/echo metadata, acknowledgement presence, notification/opcode observations and status control checks. Never log decrypted frames or PINs. A timeout with no acknowledgement is not an empty slot or conclusive proof that firmware lacks the command.

**HA-only initialization (last resort)** is destructive, not a diagnostic. Do not select it for read testing. Its clear-all command has synthetic frame/authorization coverage; a live clear-all was executed under explicit administrator authorization and returned HTTP 200 `initialized=true`; the subsequently restored HA code physically unlocked the door and the previous official-app code was rejected on ASL-05 firmware 1.1.30 / keypad 2.27.0, confirming the initialization baseline. It erases all keypad codes on the configured ASL-05, not ownership or pairing, only after explicit administrator confirmation. Uncertain attempts retain recovery evidence and never automatically retry. A separate request and recovery plan are needed before a live clear-all test. Cloud records are not deleted by the local command; official-app synchronization can reintroduce codes.

Do not automatically reset, unpair, remove ownership, delete accounts, revoke keys, program PINs, alter timers, or enable arrival-unlock automations to troubleshoot connectivity. Check discovery, proxy reachability, existing integration state, and sanitized errors first. A missing advertisement or timeout does not identify the cause.

Factory-reset credential testing remains a separate, destructive experiment requiring explicit approval and a recovery path. The baseline/post-reset procedure is in [BOOTSTRAP_ENROLLMENT.md](BOOTSTRAP_ENROLLMENT.md). Do not enable the experimental enrollment code to perform it.
