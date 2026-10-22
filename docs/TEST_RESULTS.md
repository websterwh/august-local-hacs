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

At the time of the 0.10.7 verification, live HA inspection found no configured official August account, so actual OAuth login/refresh and physical key validation were not acceptance-tested.

### 0.10.8 PIN capacity and arrival changes

Passed: 14 manager tests, 8 occupancy tests and the existing 32 setup tests (**54 Python tests**), plus `node tests/test_panel.js` and JavaScript syntax checking. Focused fatal-error/undefined-name Ruff checks passed for the modified Python integration files; this is not a claim of project-wide lint cleanliness. The isolated dependency check passed. No hardware suite was run.

The focused suites cover automatic per-user assignment, total-capacity growth, manual extra PINs, migration of metadata-only ranges, duplicate/unknown occupancy, occupied slots, rejection recovery, interrupted writes, ownership protection and prevention of imported-schedule widening. Read-only occupancy tests validate slot echo, result code and credential-field parsing; timeouts never mean empty. The Node UI checks cover capacity-mode submissions, unified arrival navigation and the disabled-by-default, fresh-proximity arrival condition. These are synthetic tests, not a physical keypad acceptance test.

Live read-only storage inspection found one HA-created record marked active and nine metadata-only reservations. That old active flag represented a command acknowledgement, not proof the keypad accepted the PIN. The cause of the reported physical PIN failure remains unresolved. Direct read-only cloud diagnostics returned HTTP 403 and the supervisor core proxy returned HTTP 401; no reliable remote occupancy inventory was obtained. No test PIN was written because no unused physical slot was verified. No PIN was cleared, ownership changed or motor operation sent.

Weekly/day/time native scheduling was not established. The panel reports that limitation, rejects schedule payloads instead of silently programming unrestricted access, and blocks replacing restricted imported codes locally. A working auto-lock operation does not establish keypad pairing, PIN validity or schedule enforcement.

### 0.10.9 operation feedback and preflight classification

Passed: 18 manager/adapter tests, 8 occupancy tests and 32 setup tests (**58 Python tests**), the Node frontend checks, JavaScript syntax checking and focused fatal-error/undefined-name Ruff checks. These are synthetic regression checks, not a live keypad or visual browser acceptance test.

The manager/adapter tests distinguish the two fixed "no PIN insertion sent" preflight failures from genuinely uncertain writes. Only a proven preflight block discards the new unsent candidate; existing uncertain records are preserved. The Node tests cover a visible busy indicator, duplicate-submit suppression, restoration of normally disabled/enabled controls, and cleanup after request, refresh and rendering failures. A successful write followed by a failed status refresh is not retried or reported as a failed write.

Read-only HA storage inspection found a needs-attention record with a pending candidate but no confirmed PIN. Its underlying failure stage cannot be reconstructed from that record alone; no candidate was discarded or lock operation sent. Hardware PIN acceptance and recovery remain unverified.

### 0.10.10 disconnection and settings responsiveness

Passed: 19 manager/adapter tests, 9 occupancy tests, 2 auto-lock lifecycle tests and 32 setup tests (**62 Python tests**), plus JavaScript syntax and Node frontend checks. Deferred frontend reads cover immediate rendering, duplicate-click suppression, close/switch invalidation, reusing a pending read after reopening, retry after failure and returning to arrival settings. These are mock-DOM checks, not live HA visual/browser acceptance tests.

The upstream `DisconnectedError` derives from the Yale BLE error base, not `BleakError` or `RuntimeError`. Previous occupancy handlers missed it. Read-only discovery now classifies it as unknown occupancy, and a disconnect during initial discovery connection returns an actionable no-write error while releasing the operation lock. A pre-insertion occupancy disconnect reports that insertion did not start. An auto-lock read error no longer suggests a setting save may have occurred.

Auto-lock renders before the device read, uses HA card/loading components, keeps Close available while reading and disables Save until a successful read. The panel is still a custom HA panel; this is not a complete migration to HA's built-in settings interface. Saves are never automatically retried and duplicate submissions are blocked while a save is in progress.

Regression coverage uses the actual upstream disconnect exception with mocked transport. No existing recovery record was cleared, no physical PIN acceptance was established and no lock setting or motor operation was sent during this update.

Do not run the hardware component suite as a default regression gate: it contains experimental Bluetooth writes. See [LOCAL_TESTING.md](LOCAL_TESTING.md).

Factory-reset survival of existing BLE keys and cloud-token validity are separate, untested questions. Reset, ownership removal, revocation and account deletion are not interchangeable tests. The future explicitly approved experiment is documented in [BOOTSTRAP_ENROLLMENT.md](BOOTSTRAP_ENROLLMENT.md).
