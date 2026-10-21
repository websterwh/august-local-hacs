# August Local Keypad (Door PINs)

A Home Assistant custom integration that adds local PIN/keypad management, lock-native auto-lock control, and HA-side proximity-based arrival automation on top of the existing **Yale Access Bluetooth** (`yalexs_ble`) integration.

**This does not replace the August app, does not perform factory enrollment, and does not pair a keypad from scratch.** It manages PINs on a lock that is **already commissioned** (has an installed Bluetooth offline key) via Yale Access Bluetooth, and whose physical keypad is **already paired**.

## What this actually does

- Imports a lock's already-installed Bluetooth offline key, either by reusing Home Assistant's official **August** integration's OAuth session, or via a legacy email/password sign-in (not guaranteed to work — see Limitations).
- Adds/changes/deletes PINs on explicitly owned or explicitly-reserved keypad slots over the existing Yale Access Bluetooth connection.
- Per-user PIN self-service: non-admin HA users manage only PINs assigned to them; admins manage all.
- Reads/writes the lock's native auto-lock timer (works without HA running, since it's stored on the lock).
- Passive Bluetooth-beacon "near door" detection plus a generated arrival-unlock automation, using HA Companion app / BLE beacon proximity — not location alone.
- A sidebar panel (`Door PINs`) for PIN management instead of YAML service calls.

## What this does **not** do

- **No factory commissioning.** A factory-reset lock cannot be enrolled by this integration. You need an already-commissioned lock with an installed owner key.
- **No keypad pairing.** The physical August Smart Keypad must already be paired to the lock through the official app before this integration can program PINs on it. HA-only keypad pairing is unimplemented and unverified.
- **No PIN readback from the lock.** PIN contents cannot be reliably enumerated from tested ASL-05 firmware (1.1.30). The integration retains PINs it wrote, in its own local storage — it never assumes an unreserved slot is empty, and it never guesses a PIN.
- **No cloud account required for day-to-day operation.** The August cloud account is used once, optionally, to import the already-provisioned key; local PIN writes do not reach August's servers.

## Requirements

- Home Assistant 2024.1+
- A Bluetooth adapter or proxy (e.g. ESPHome Bluetooth proxy) within range of the lock
- An August ASL-05 lock already commissioned with an installed Bluetooth offline key (via the official August app, at least once)
- The [Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) integration already set up and working for that lock

## Installation (HACS)

1. Home Assistant → **Settings → Devices & Services → Integrations**
2. **⋮ → Custom repositories** → add `https://github.com/websterwh/august-local-hacs`, category **Integration**
3. Install **August Local Keypad (Door PINs)**, restart Home Assistant
4. **Settings → Devices & Services → Add Integration** → search "August Local Keypad"
5. Choose **Use an existing HA Bluetooth lock** (if Yale Access Bluetooth is already set up), or **Use August account connected to HA** to import the key via your existing official August integration's session

## Using it

Open **Door PINs** in the HA sidebar to manage PINs through the panel: reserve a slot range dedicated to HA, create/assign/delete PINs, read/set the auto-lock timer, and configure arrival-based auto-unlock. Service calls (`august_local_keypad.program`, `.insert`, `.delete`, `.status`) are also available for automations — see `services.yaml`.

## Safety notes

- Programming an **owned** slot clears it with its current PIN before setting a new one; a failure partway through can leave that slot empty — this is a lock-firmware limitation, not a bug to "fix" by retrying blindly.
- **Insert** (used for freshly reserved, never-before-used slots) never sends a clear command, and the lock accepts inserts into occupied slots too — only use it on a range you've confirmed is unused.
- The integration never logs PIN values, offline keys, or raw decrypted BLE frames; failures report only a stage name and exception type.

## Documentation

See [`custom_components/august_local_keypad/README.md`](custom_components/august_local_keypad/README.md) for the integration's own setup notes, and `services.yaml` for the service schema.

## Credits / related projects

- [HA August](https://www.home-assistant.io/integrations/august/) — cloud account integration this reuses for key import
- [HA Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) — local Bluetooth transport this integration operates over
- [yalexs](https://github.com/Yale-Libs/yalexs) / [yalexs-ble](https://github.com/Yale-Libs/yalexs-ble) — underlying account and Bluetooth libraries

## License

MIT — see [LICENSE](LICENSE). Not affiliated with August Home Inc. or Yale.
