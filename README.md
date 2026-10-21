# August Local Keypad (Door PINs)

A Home Assistant custom integration that adds local PIN/keypad management, lock-native auto-lock control, and HA-side proximity-based arrival automation on top of the existing **Yale Access Bluetooth** (`yalexs_ble`) integration.

**This integr integrates locks that have been provisioned with a Bluetooth offline key via August's servers.** Factory-reset locks require a one-time August account setup (detailed below). After provisioning, the lock operates 100% offline with HA—no August cloud required. Keypad pairing is managed separately via the August app and is a prerequisite.

## What this actually does

- Imports a lock's already-installed Bluetooth offline key, either by reusing Home Assistant's official **August** integration's OAuth session, or via a legacy email/password sign-in (not guaranteed to work — see Limitations).
- Adds/changes/deletes PINs on explicitly owned or explicitly-reserved keypad slots over the existing Yale Access Bluetooth connection.
- Per-user PIN self-service: non-admin HA users manage only PINs assigned to them; admins manage all.
- Reads/writes the lock's native auto-lock timer (works without HA running, since it's stored on the lock).
- Passive Bluetooth-beacon "near door" detection plus a generated arrival-unlock automation, using HA Companion app / BLE beacon proximity — not location alone.
- A sidebar panel (`Door PINs`) for PIN management instead of YAML service calls.

## What this does **not** do

- **HA-only factory enrollment.** Factory-reset locks require a one-time August account to receive the encryption key. See [BOOTSTRAP_ENROLLMENT.md](docs/BOOTSTRAP_ENROLLMENT.md).
- **No keypad pairing.** The physical August Smart Keypad must already be paired to the lock through the official app before this integration can program PINs on it. HA-only keypad pairing is unimplemented and unverified.
- **No PIN readback from the lock.** PIN contents cannot be reliably enumerated from tested ASL-05 firmware (1.1.30). The integration retains PINs it wrote, in its own local storage — it never assumes an unreserved slot is empty, and it never guesses a PIN.
- **Zero cloud contact after setup.** Once keyed via August account (one-time), all future operations are local Bluetooth. August servers are never contacted again.

## Requirements

- Home Assistant 2024.1+
- A Bluetooth adapter or proxy within range of the lock
- An August ASL-05 lock (factory-reset, commissioned, or already paired)
- The [Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) integration

## Installation & Setup

1. Home Assistant → **Settings → Devices & Services → Integrations**
2. **⋮ → Custom repositories** → add `https://github.com/websterwh/august-local-hacs`, category **Integration**
3. Install **August Local**, restart Home Assistant
4. **Settings → Devices & Services → Add Integration** → search "August Local"
5. Choose setup option:
   - **Enroll a factory-reset lock** (for new/reset ASL-05)
   - **Use an existing Bluetooth lock** (Yale Access Bluetooth)
   - **Use August account** (optional, import key from app)

## Using it

Open **Door PINs** in the HA sidebar to manage PINs through the panel: reserve a slot range dedicated to HA, create/assign/delete PINs, read/set the auto-lock timer, and configure arrival-based auto-unlock. Service calls (`august_local_keypad.program`, `.insert`, `.delete`, `.status`) are also available for automations — see `services.yaml`.

## Safety notes

- Programming an **owned** slot clears it with its current PIN before setting a new one; a failure partway through can leave that slot empty — this is a lock-firmware limitation, not a bug to "fix" by retrying blindly.
- **Insert** (used for freshly reserved, never-before-used slots) never sends a clear command, and the lock accepts inserts into occupied slots too — only use it on a range you've confirmed is unused.
- The integration never logs PIN values, offline keys, or raw decrypted BLE frames; failures report only a stage name and exception type.

## Documentation

- [SETUP.md](docs/SETUP.md) — Full installation & usage guide
- [TEST_RESULTS.md](docs/TEST_RESULTS.md) — Local component testing (7/7 passing)
- [LOCAL_TESTING.md](docs/LOCAL_TESTING.md) — Debugging guide
- [custom_components/august_local/README.md](custom_components/august_local/README.md) — Integration details

## Credits / related projects

- [HA August](https://www.home-assistant.io/integrations/august/) — cloud account integration this reuses for key import
- [HA Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) — local Bluetooth transport this integration operates over
- [yalexs](https://github.com/Yale-Libs/yalexs) / [yalexs-ble](https://github.com/Yale-Libs/yalexs-ble) — underlying account and Bluetooth libraries

## License

MIT — see [LICENSE](LICENSE). Not affiliated with August Home Inc. or Yale.
