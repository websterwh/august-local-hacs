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

### 0.10.11 known-slot PIN regression repair

The original insert service did not require opcode 0x39. Version 0.10.8 introduced an unconditional occupancy probe even after an acknowledged HA deletion; the later preflight handler also replaced the cleared record with an unverified reservation. This blocked the original delete/re-add workflow independently of whether the new automatic-discovery feature worked. Known-PIN replacement continues to use the original protocol transaction without discovery.

Confirmed-cleared HA slots now authorize a one-use insertion proof bound to the same pending PIN and slot. The proof is persisted as consumed before programming and discarded on restart. Newly discovered/unknown slots and direct insert calls without a proof still require the occupancy read. Explicit recovery clears retained HA candidates in one existing slot, then inserts only after all clears succeed. Old blocked records without retained candidates require an administrator's last known HA-created PIN and explicit clear confirmation; no slot is silently assumed empty.

Passed: 29 manager/adapter tests, 12 occupancy/insertion tests, 2 auto-lock tests and 32 setup tests (**75 Python tests**), plus Node frontend and JavaScript syntax checks. Coverage includes confirmed delete/re-add with occupancy forced to fail, proof consumption before insertion, stale-proof rejection, original known-code replacement, recovery ordering, unsuccessful clear blocking replacement, ownership checks and explicit last-known-code restoration.

Read-only live inspection found the affected slot as an unverified reservation with no retained code. No live registry values were edited and no PIN, setting or motor operation was sent. This release repairs the demonstrated software regression; physical keypad acceptance and automatic discovery on this lock remain unverified. Never turn missing inventory responses into free slots.

Do not run the hardware component suite as a default regression gate: it contains experimental Bluetooth writes. See [LOCAL_TESTING.md](LOCAL_TESTING.md).

### Subsequent physical verification and read investigation

After the release checks above, the user physically verified an August-created baseline in slot 26 and then a single HA **Change PIN** transaction in existing slot 1. Both unlocked the door. This verifies that known-slot transaction and keypad acceptance; it does not verify INSERT, free-slot reads, full capacity or schedules. Neither code was silently removed after the tests. No PIN values belong in this report.

Read-only cloud inventory succeeded with the Yale/August brand configuration, verifying the loaded official record at slot 26. Earlier default-brand HTTP 403 was not evidence that the inventory endpoint was unsupported. Cloud omissions still do not establish physical emptiness.

The first live read through HA's existing Bluetooth adapter returned **TIMEOUT at known-occupied slot 1**, with no matching acknowledgement observed. The panel reported the actual timeout instead of a capacity shortage. No allocation or PIN-changing command followed. Separate standalone proxy attempts failed during connection, before any occupancy request; they are not firmware-capability evidence.

A subsequent server-side comparison of **slots 1 and 26** allowed the full upstream response window. Both returned TIMEOUT with `ack_seen=False`, `notifications_seen=False` and no response opcodes observed. Ordinary lock-status reads succeeded immediately before and after each occupancy probe. This establishes a command-specific lack of response on the tested authenticated legacy path, rather than proving fullness or a disconnected link. Static native request construction agrees with opcode `0x39` and the little-endian slot field; the SDK calls that builder a Unity keycode read. No alternative supported ASL-05 occupancy-read mechanism has been validated. This does not prove that every firmware/channel lacks PIN reads.

Further read-only analysis of the current official app found that its `0x39` wrapper is a Unity master-code read, not an established legacy slot-enumeration API. Its legacy credential workflow obtains slot assignments from the cloud and updates individual credentials; ordinary synchronization is not a global clear. No physical-empty inventory mechanism was established. This does not make cloud omissions safe allocation evidence or establish why the tested firmware is silent. No cloud reservation or synchronization request was executed during this research.

The unreleased diagnostic path distinguishes rejected results, incorrect slot echoes, malformed BCD fields, disconnects and timeouts. It observes acknowledgements without accepting them as occupancy responses. Single-slot probes allocate nothing; status control reads and safe notification/opcode metadata help distinguish an unresponsive link from a command-specific failure. Automatic free-slot discovery remains unverified until a correct successful response is observed on this device.

The separate last-resort HA-only initialization path requires administrator confirmation, a persistent one-use authorization and a successful clear-all result before exposing HA-cleared slots. It is never invoked by discovery failure, ordinary provisioning or startup. Its clear-all behaviour had **not been exercised on hardware** at that time; no reset, unpairing or clear-all was needed for the physically successful known-slot repair. Native scheduling and factory commissioning remain unverified.

Passed **137 focused synthetic Python tests**: 40 inventory, 42 manager/adapter, 14 initialization/API/control-read, 7 clear-all protocol, 2 auto-lock and 32 setup regressions. Node frontend checks and JavaScript syntax checks passed. Focused fatal-error/undefined-name Ruff and formatter checks passed. Clear-all tests use mock frames only; none of these gates issues hardware writes. The live deployment passed HA configuration checks. The private one-shot comparison hook was removed from the deployed source after the read-only test; no clear-all, code change or automated motor command was sent.

Subsequent exclusive-capacity changes passed **141 focused synthetic Python tests**: the manager suite increased to 46 tests; the other suite counts above are unchanged. After successful explicit initialization, growth uses only slots without existing records and requires ready/exclusive state, consumed authorization and an initialized receipt. Tests cover growth without another clear or occupancy read, preservation of uncertain records, incomplete initialization and interrupted/restarted initialization. Frontend checks cover the whole-lock exclusivity warning and the distinct HA-only provisioning action. Node syntax/frontend, focused Ruff and nine-file formatter checks passed. These subsequent capacity changes were deployed: the HA core configuration check and restart succeeded. A live initialization sequence followed; see below.

### Authorized live initialization sequence

The administrator explicitly authorized erasure and confirmed an alternative entry before proceeding. Both prior known codes were privately backed up in HA storage with restricted permissions. Latest manager and panel safeguards were deployed; the HA core configuration check and restart succeeded.

One valid one-use initialization request returned HTTP 200 with `initialized=true`, `allocated=2`, `assigned=2`; the guarded clear-all was acknowledged. A subsequent capacity-growth request returned `allocated=1`, `total=3`, `assigned=2`, `allocation_source=ha_only_initialization` without another erase or read. Initialization state: ready/exclusive; authorization consumed; request history count 1.

The existing manually entered HA code (same value, no generation) was restored into its owner's newly assigned slot 2 using the acknowledged initialization clearance. Programming response: HTTP 200, `state=programmed_unverified`, no pending candidate. Slots 1 and 3 are cleared/empty locally; slot 2 is `programmed_unverified`.

Physical keypad acceptance of the restored HA code and rejection of the previous official-app code are **confirmed** on ASL-05 firmware 1.1.30 / keypad 2.27.0: the restored HA code unlocked the door; the previous official-app code was rejected. This validates the initialization baseline and post-initialization PIN insertion into slot 2 (newly assigned after clear-all). Slots 1 and 3 remain locally cleared; slot 2 remains `programmed_unverified` because no software state transition for physical confirmation was implemented. No further PIN or hardware action was taken after the user's confirmation. No factory reset, unpairing, ownership change, cloud mutation or automated motor command was executed.

### Arrival-unlock guard repair and proximity calibration

Inspection found an enabled arrival automation and a functioning phone beacon, but the configured RSSI cutoff rejected measured near-door signals. A controlled phone-at-door check measured approximately -70 to -65 dBm; calibration to -72 dBm subsequently produced a real near-door `on` state at -71 dBm. This is installation-specific calibration, not a recommended universal threshold.

The v27 generator used away/home state timestamps, rejected undefined trigger data and future proximity timestamps, tied the waiting run to the same arrival, and rechecked live proximity immediately before unlocking. Subsequent real GPS testing exposed the timestamp assumption described below; the earlier synthetic success did not establish real tracker compatibility. The five-minute configured away requirement and 30-minute fail-closed wait were retained.

Passed **152 focused synthetic Python tests** (the earlier 141 plus 11 proximity gate/lifecycle tests), Node frontend/syntax checks, focused Ruff and formatter checks. The exact generated guard expressions also passed **24 isolated fixture scenarios rendered by the live HA template API**; these rendered templates did not change real GPS/proximity states or execute lock actions. Updated frontend v27 and the guarded target configuration were deployed; HA core configuration check and restart succeeded. Real departure/return testing was unavailable, so an isolated simulated-arrival verification was prepared with actual proximity, phone-home and closed-door checks. No automatic-unlock success is claimed from the software checks alone.

A separately authorized **controlled simulated arrival successfully ran the automation and changed the real lock state from locked to unlocked**. The temporary tracker spent the full configured five-minute period away before one return-home transition. The generated arrival guards remained intact, with additional real phone-home and closed-door conditions; live Bluetooth proximity and freshness were not fabricated. The phone's actual GPS/location state was not changed. This verifies the controlled arrival/action and real lock path, not real-world GPS/background tracking reliability.

The temporary test automation and tracker were removed and confirmed absent, with no residual test entity-registry entry. The production automation's configuration was unchanged by the isolated test and was restored enabled. Final observed state: door closed, lock unlocked, production arrival automation on. No repeat unlock, PIN operation, reset, ownership change or relock command was issued during cleanup.

### Forced GPS update timing regression (2026-10-26)

A real arrival trace on HA 2026.10.4 stopped at the first condition: the prior GPS state timestamp described only the latest sample, roughly 23 seconds before return, despite recorded absence exceeding an hour. Same-state reports also refreshed home timestamps, invalidating the old same-arrival comparison. This was an automation timing defect, distinct from previously observed Companion delivery failures.

Frontend v28 measures continuous known-away truth with a template trigger's `for` period and requires the captured departure to originate at home. Immediate restart/cancellation triggers invalidate old runs on any new departure or unknown/unavailable location; cancellation is not blocked by top-level conditions. Eligibility is deliberately lost on reload/restart. Return-home and locked-at-return checks precede the 30-minute proximity wait, and fresh post-return proximity, current home state and locked state are checked again before the action.

All **152 focused Python regressions**, Node generator assertions and syntax checks passed, along with scoped fatal-error Ruff, Python formatting and whitespace checks. **13 isolated behavioral scenarios executed in live HA** using only temporary diagnostic entities, a one-second test-only away period, and a private diagnostic event replacing the unlock action. Covered startup already away; repeated location samples and named-away-zone changes; short trips; unknown/unavailable during arming and after arming; departure or unknown during proximity wait; stale, future and pre-arrival samples; fresh post-arrival samples after home updates; unlocked before the final action; and arrival while unlocked followed by manual locking. The test configuration contained no service actions, real phone/proximity states were untouched, and temporary configurations/entities were removed. No motor operation was issued. This verifies HA automation behavior, not a successful real departure/return unlock with the repaired configuration.

The existing production automation was explicitly updated with its original source, proximity sensor, lock and 300-second minimum; new generated automations remain disabled by default. HA configuration check and restart succeeded. Deployed source hashes and the saved production configuration matched the corrected generator, frontend registration used v28, the production automation was enabled, and the lock remained locked. No temporary test entities or entity-registry entries remained. The next real test must begin with a new departure after deployment.

### Onboard auto-lock mode and BLE proximity accumulator repairs (2026-10-26)

Live real-arrival testing revealed three independent physical factors:
1. **Onboard Auto-Lock Mode:** The physical lock hardware was set to `timer` mode with a 300-second timer. In August firmware, `timer` mode relies on DoorSense to confirm the door was opened and closed before engaging. Since DoorSense (`binary_sensor.front_door_door`) has remained uncalibrated/inactive (`off`), the lock never initiated the auto-lock countdown, leaving the door unlocked during the user's absence. The lock setting was switched to `instant` mode (`seconds=300`), which runs an autonomous 5-minute countdown timer on the lock's processor every time after unlocking without requiring DoorSense. Verified confirmed on lock hardware via opcode 0x04.
2. **Proximity RF Accumulator (`NearGate`):** Previously, any single multipath dip below threshold or gap >3s wiped the sample accumulator to zero. In practice, Android background BLE bursts arrive 3–6s apart and packet RSSI varies by ±8 dBm when approaching a door. `NearGate` was upgraded to a decaying accumulator with an 8-second inter-packet gap limit. Single dips decrement sample count rather than destroying the 2-second ramp-up, allowing sustained near-door presence to reliably trigger proximity. All 11 proximity tests in `test_nearby.py` passed.
3. **Arrival Automation Sequence:** Removed the premature `lock == locked` check at the instant of entering the GPS home zone. The automation now waits for near-door proximity, checking that the lock is locked immediately prior to the unlock command. If the lock was already unlocked, the unlock action is safely skipped.
4. **Custom Element Aliases:** `panel.js` registers backwards-compatible custom element aliases (`august-pin-manager-v28`, `august-pin-manager-v27`, and `august-pin-manager`) inside a safe registration loop to prevent blank screens caused by browser/app frontend caching. All 152 Python tests and Node frontend assertions passed.

Factory-reset survival of existing BLE keys and cloud-token validity are separate, untested questions. Reset, ownership removal, revocation and account deletion are not interchangeable tests. The future explicitly approved experiment is documented in [BOOTSTRAP_ENROLLMENT.md](BOOTSTRAP_ENROLLMENT.md).
