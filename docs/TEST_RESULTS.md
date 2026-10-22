# August Local: Test Evidence and Limits

## Earlier component-test reports are not enrollment verification

Earlier reports described `tests/test_all_components.py` as “7/7 passing” and production-ready. Those conclusions are withdrawn. They did not establish authenticated factory enrollment, a successfully installed offline key, or end-to-end lock control. Historical reports are not a fresh hardware test in this change.

The reported checks and their actual evidentiary limits:

| Reported check | What it can establish | What it cannot establish |
|---|---|---|
| BLE discovery and connection | Advertisement/transport visibility at that time | Authentication or owner permission |
| Advertisement byte slicing | Bytes were available | That the fields are enrollment nonces |
| Concatenating two fields | A 16-byte result | A negotiated session key |
| Random-byte generation | Local random data generation | A persistent key installed on the lock |
| AES frame construction | Local cipher execution | Correct frame layout, checksum, slot, handshake, or lock acceptance |
| GATT write without transport error | Transport accepted a write | Authenticated command acceptance, persistence, or state change |
| A failed all-zero-key attempt | An attempt failed | Valid cryptographic rejection, default-key impossibility, or successful authentication with a real key |

No verified decrypted factory-commissioning HTTP exchange was recovered in this change. The four `index*.html` capture files inspected are classic PCAP files, not HTML or PCAPng containers with decryption-secret blocks. This does not rule out separately exported session keys or other recovery sources. Captures remain private and are not release artifacts.

## Current verification boundary

`tests/test_setup_regressions.py` contains synthetic setup regression checks using mocked Home Assistant/Bluetooth behavior. These exercise software branches; they do not test a running HA instance, Bluetooth proxies, the live August API, factory registration, calibration, keypad pairing, or motors.

For version 0.10.7, the following command passed **32 synthetic tests** in an isolated Python environment:

```bash
python -m unittest discover -s tests -p 'test_setup_regressions.py' -v
```

Coverage includes the no-account guidance and retry path, loaded-account selection and stale-selection rejection, borrowing a refreshed official-session token on every discovery call, discovery of an installed owner key, cleanup without closing the shared session, sanitized account failures, rejection of a different lock before Bluetooth access, invalid-key rejection, sequential key fallback, and separation of transport failures from invalid keys. Ruff passed for `account.py` and `config_flow.py`; the isolated environment's dependency check passed.

Live HA inspection found no configured official August account, so actual OAuth login/refresh and physical key validation were not acceptance-tested. The user must complete sign-in through the official August integration. No account was created or changed, and no lock operation was sent.

Do not run the hardware component suite as a default regression gate: it contains experimental Bluetooth writes. See [LOCAL_TESTING.md](LOCAL_TESTING.md).

Factory-reset survival of existing BLE keys and cloud-token validity are separate, untested questions. Reset, ownership removal, revocation and account deletion are not interchangeable tests. The future explicitly approved experiment is documented in [BOOTSTRAP_ENROLLMENT.md](BOOTSTRAP_ENROLLMENT.md).
