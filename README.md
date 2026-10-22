# August Local Keypad (Door PINs)

A Home Assistant custom integration that adds local PIN/keypad management, lock-native auto-lock control, and HA-side proximity-based arrival automation on top of the existing **Yale Access Bluetooth** (`yalexs_ble`) integration.

**This integration works with August ASL-05 locks that already have an offline Bluetooth key provisioned through an August account.** The setup wizard imports the lock's installed key from an existing August account and validates it locally over BLE. Factory-reset locks without a provisioned key and locks requiring new key installation are not yet supported.

## What this actually does

- Imports a lock's already-installed Bluetooth offline key via the official HA August integration's OAuth session.
- Validates the imported key against the physical lock over BLE without moving the deadbolt.
- Configures Yale Access Bluetooth (`yalexs_ble`) for local BLE control and adds the Door PINs panel.
- Adds/changes/deletes PINs on explicitly owned or reserved keypad slots over the local BLE connection.
- Per-user PIN self-service: non-admin HA users manage only PINs assigned to them; admins manage all.
- Reads/writes the lock's native auto-lock timer (stored on the lock, works without HA running).
- Passive Bluetooth-beacon "near door" detection plus a generated arrival-unlock automation using HA Companion app / BLE beacon proximity — not location alone.
- A sidebar panel (`Door PINs`) for PIN management instead of YAML service calls.

**Credential handling:** August Local borrows API access from the official HA August integration and never logs, stores, or exports the account token or password. Token persistence and refresh are handled entirely by the official integration. The validated BLE key and slot are stored by `yalexs_ble` in HA config. The official August integration may independently contact August's cloud. Local BLE control does not guarantee the lock's WiFi module never contacts August's cloud, nor does it guarantee key permanence.

## What this does **not** do

- **No factory enrollment.** Factory-reset locks require an August account to receive an initial offline key. The wizard imports an already-provisioned key but cannot register a new lock or install a new offline credential. See [BOOTSTRAP_ENROLLMENT.md](docs/BOOTSTRAP_ENROLLMENT.md).
- **No keypad pairing.** The physical August Smart Keypad must already be paired to the lock through the official app. HA-only keypad pairing is unimplemented and unverified.
- **No PIN readback from the lock.** PIN contents cannot be reliably enumerated from tested ASL-05 firmware. The integration retains PINs it wrote, in its own local storage — it never assumes an unreserved slot is empty and never guesses a PIN.
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

Open **Door PINs** in the HA sidebar to manage PINs through the panel: reserve a slot range dedicated to HA, create/assign/delete PINs, read/set the auto-lock timer, and configure arrival-based auto-unlock. Service calls (`august_local.program`, `august_local.insert`, `august_local.delete`, `august_local.status`) are also available for automations — see `services.yaml`.

## Safety notes

- Programming an **owned** slot clears it with its current PIN before setting a new one; a failure partway through can leave that slot empty — this is a lock-firmware limitation, not a bug to "fix" by retrying blindly.
- **Insert** (used for freshly reserved, never-before-used slots) never sends a clear command, and the lock accepts inserts into occupied slots too — only use it on a range you've confirmed is unused.
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
