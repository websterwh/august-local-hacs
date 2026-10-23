# August Local Keypad (Door PINs)

A Home Assistant custom integration that adds local PIN/keypad management, lock-native auto-lock control, and HA-side proximity-based arrival automation on top of the existing **Yale Access Bluetooth** (`yalexs_ble`) integration.

**This integration works with August ASL-05 locks that already have an offline Bluetooth key provisioned through an August account.** The setup wizard imports the lock's installed key from an existing August account and validates it locally over BLE. Factory-reset locks without a provisioned key and locks requiring new key installation are not yet supported.

## What this actually does

- Imports a lock's already-installed Bluetooth offline key via the official HA August integration's OAuth session.
- Validates the imported key against the physical lock over BLE without moving the deadbolt.
- Configures Yale Access Bluetooth (`yalexs_ble`) for local BLE control and adds the Door PINs panel.
- Discovers PIN capacity using acknowledged local occupancy reads, with one slot per HA user or a chosen total, plus manually added PINs. Unknown slots are never allocated.
- Per-user PIN self-service: non-admin HA users manage only PINs assigned to them; admins manage all.
- Reads/writes the lock's native auto-lock timer (stored on the lock, works without HA running).
- Passive Bluetooth-beacon "near door" detection plus a generated arrival-unlock automation using HA Companion app / BLE beacon proximity — not location alone.
- A sidebar panel (`Door PINs`) for PIN management instead of YAML service calls.

**Credential handling:** August Local borrows API access from the official HA August integration and never logs, stores, or exports the account token or password. Token persistence and refresh are handled entirely by the official integration. The validated BLE key and slot are stored by `yalexs_ble` in HA config. The official August integration may independently contact August's cloud. Local BLE control does not guarantee the lock's WiFi module never contacts August's cloud, nor does it guarantee key permanence.

## What this does **not** do

- **No factory enrollment.** Factory-reset locks require an August account to receive an initial offline key. The wizard imports an already-provisioned key but cannot register a new lock or install a new offline credential. See [BOOTSTRAP_ENROLLMENT.md](docs/BOOTSTRAP_ENROLLMENT.md).
- **No keypad pairing.** The physical August Smart Keypad must already be paired to the lock through the official app. HA-only keypad pairing is unimplemented and unverified.
- **Discovery depends on firmware support.** Slot reads are not verified on this installation. Unsupported reads/timeouts stop provisioning; cloud-list omissions and old range reservations are not proof of empty slots.
- **Scheduled PINs are not implemented.** Day/time restrictions remain in the August app. Local replacement of a restricted imported PIN is blocked rather than changing it to unrestricted access.
- **No guaranteed cloud-free operation.** Local BLE control reduces cloud dependence but does not prevent the lock's own WiFi or the official August integration from contacting August servers.

## Requirements

- Home Assistant with the current August and Yale Access Bluetooth integrations; minimum-version compatibility is not verified
- A Bluetooth adapter or proxy within range of the lock
- An August ASL-05 lock already registered to an August account with an installed offline key
- The [Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) integration (configured by this wizard, or pre-existing)
- The [official HA August integration](https://www.home-assistant.io/integrations/august/) loaded and signed in — August Local borrows its account access

## Installation & Setup

1. Open **HACS** in Home Assistant
2. **⋮ → Custom repositories** → add `https://github.com/websterwh/august-local-hacs`, category **Integration**
3. Install **August Local**, restart Home Assistant
4. First add the official August integration if not already loaded: [Settings → Devices & Services → August](https://my.home-assistant.io/redirect/config_flow_start?domain=august) and complete its supported authentication
5. **Settings → Devices & Services → Add Integration** → search "August Local"; press **Submit** when the setup_august guidance appears, then choose the loaded August account under **Choose your connected August account**
6. Select an already registered account lock, then confirm BLE key validation (no motor movement). Existing Yale Access Bluetooth credentials can be updated for that same lock.

No password is entered or stored by August Local. Account errors point you back to the official August integration, not a separate password form. Factory registration, calibration, and keypad pairing are not part of this wizard yet.

## Using it

Open **Door PINs** and choose **Provision PIN capacity**, then **Add PIN**. A programming acknowledgement is not a physical keypad acceptance test. **Arrival unlock** now groups phone-proximity calibration and the arrival automation; generated automations remain disabled until explicitly enabled. Auto-lock remains separate. Service calls (`august_local.program`, `august_local.insert`, `august_local.delete`, `august_local.status`) remain available — see `services.yaml`.

Existing HA-managed PINs do not require automatic discovery to change. After an acknowledged HA deletion, **Add PIN** can reuse that same exclusively HA-managed slot without a slot-read probe. An uncertain record offers **Recover / replace**; an old blocked record whose candidate was discarded offers admin-only **Restore known HA slot**, requiring its last known HA PIN. Recovery clears only the specified known candidates, and stops unless every clear is acknowledged. It never discovers or erases unknown codes.

Under **Advanced PIN setup**, administrators can **Read slot occupancy** without allocating capacity or changing codes. Unknown, rejected and timed-out reads are reported separately; none means the slot is free or the lock is full. The tested ASL-05 currently times out reading a known working slot, so automatic discovery remains unverified.

**HA-only initialization (last resort)** is a separate, destructive opt-in: it erases **all keypad PINs on the configured ASL-05**, including August-created codes, then prepares the requested HA capacity only after a successful clear-all response. It requires typing the erase confirmation and is never called automatically when discovery fails. It does not reset the lock, unpair the keypad, change ownership or operate the motor. Physical testing on ASL-05 firmware 1.1.30 with keypad 2.27.0 confirmed: after explicitly authorized HA-only initialization, a previously registered code was rejected at the keypad and a newly programmed HA-managed code was accepted. Command acknowledgement alone is not physical evidence; this result applies only to that tested hardware and does not establish arbitrary unknown-slot discovery, support for other firmware versions, total hardware capacity, native schedules, or keypad commissioning. Interrupted attempts retain credentials for recovery and never silently retry. After a confirmed clear, capacity growth can proceed without re-reading occupancy: it allocates only slots with no existing HA record, preserves all existing, uncertain, and imported records, and issues no further clear or occupancy read. All keypad code writes on the lock must remain exclusive to HA after initialization — not merely the currently allocated range — because future capacity growth depends on the entire cleared baseline. It is not necessary for changing an existing known HA PIN.

## Safety notes

- Programming an **owned** slot clears it with its current PIN before setting a new one; a failure partway through can leave that slot empty — this is a lock-firmware limitation, not a bug to "fix" by retrying blindly.
- **Insert** requires a fresh occupancy read unless the manager supplies a one-use proof of an acknowledged HA clear for that same slot/candidate. Keep HA-managed slots exclusive to HA. The protocol can otherwise accept an occupied slot; it must never be used as a write-based occupancy probe.
- The integration never logs PIN values, offline keys, or raw decrypted BLE frames; failures report only a stage name and exception type.

## Documentation

- [SETUP.md](docs/SETUP.md) — Full installation & usage guide
- [BOOTSTRAP_ENROLLMENT.md](docs/BOOTSTRAP_ENROLLMENT.md) — Account-assisted key import, multiple-owner notes, and factory-reset experiment protocol
- [TEST_RESULTS.md](docs/TEST_RESULTS.md) — Local component test evidence and limitations
- [LOCAL_TESTING.md](docs/LOCAL_TESTING.md) — Debugging guide
- [custom_components/august_local/README.md](custom_components/august_local/README.md) — Integration details

## Credits / related projects

- [HA August](https://www.home-assistant.io/integrations/august/) — cloud account integration this reuses for key import
- [HA Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) — local Bluetooth transport this integration operates over
- [yalexs](https://github.com/Yale-Libs/yalexs) / [yalexs-ble](https://github.com/Yale-Libs/yalexs-ble) — underlying account and Bluetooth libraries

## License

MIT — see [LICENSE](LICENSE). Not affiliated with August Home Inc. or Yale.
