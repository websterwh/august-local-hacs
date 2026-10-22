# August Local: Local Testing

## Safe software checks

Run the synthetic setup regressions without connecting to a lock:

```bash
python -m unittest discover -s tests -p 'test_setup_regressions.py' -v
```

These checks use mocked transport/HA behavior. They do not establish real authentication, registration, key installation, calibration, keypad pairing, or motor operation. Use an isolated Python environment with the declared dependencies; do not downgrade the host's cryptography package to accommodate capture tooling.

`tests/test_all_components.py` and `tests/debug_lock_connectivity.py` access Bluetooth hardware. The former also contains experimental writes. They are **not** safe default software verification commands and are not evidence of successful enrollment. See [TEST_RESULTS.md](TEST_RESULTS.md).

## Account-assisted setup checks

The wizard imports an existing, installed owner key. It uses an already loaded official August account or direct sign-in and verification, then asks which account lock to import. Keep the proxy close to that lock. Key validation is read-only and does not intentionally move the deadbolt.

For an explicitly authorized HA acceptance test, verify:

- Failed sign-in stays an account error, not a Bluetooth error; logs contain no credentials.
- Account locks without installed offline keys cannot complete setup.
- Unreachable or rejected Bluetooth credentials cannot create an integration entry.
- Successful validation delegates the selected key/slot to Yale Access Bluetooth.
- Reconnecting an existing installation to another lock is rejected before Bluetooth validation.
- PIN records, slots, keys and unrelated account locks are not changed by failed setup.

Do not run setup concurrently with another BLE client. Direct desktop Bluetooth is not a substitute for testing HA's proxy path.

## Hardware operations require separate scope

Do not automatically reset, unpair, remove ownership, delete accounts, revoke keys, program PINs, alter timers, or enable arrival-unlock automations to troubleshoot connectivity. Check discovery, proxy reachability, existing integration state, and sanitized errors first. A missing advertisement or timeout does not identify the cause.

Factory-reset credential testing remains a separate, destructive experiment requiring explicit approval and a recovery path. The baseline/post-reset procedure is in [BOOTSTRAP_ENROLLMENT.md](BOOTSTRAP_ENROLLMENT.md). Do not enable the experimental enrollment code to perform it.
