# August Local Keypad — Setup Guide

## What this integration does

**August Local Keypad** adds PIN/keypad management, auto-lock control, and location-based auto-unlock to Home Assistant for August ASL-05 locks that already have an offline Bluetooth key installed through an August account.

Features available:
- **Key import** — import a lock's installed offline BLE key from an existing August account and validate it locally
- **PIN management** — add/change/delete codes directly from HA, per-user access control
- **Auto-lock** — timer-based automatic locking (stored on the lock, works without HA running)
- **Auto-unlock** — location + Bluetooth beacon proximity-based arrival unlock

Not yet supported or verified:
- Factory-reset enrollment (registering a new lock or installing a new offline credential)
- Keypad pairing via HA
- Calibration
- PIN readback from the lock

## Prerequisites

1. **Home Assistant** with the current August and Yale Access Bluetooth integrations; minimum-version compatibility is not verified
2. **Bluetooth adapter** or **ESPHome Bluetooth proxy** within range of the lock
3. **August ASL-05 lock** already registered to an August account with an offline key installed
4. **HACS** installed (for easy updates)
5. The [official HA August integration](https://www.home-assistant.io/integrations/august/) loaded and signed in — [add it here](https://my.home-assistant.io/redirect/config_flow_start?domain=august) if not already present

## Installation

### Via HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Click **⋮ → Custom repositories**
3. Add: `https://github.com/websterwh/august-local-hacs`
4. Category: **Integration**
5. Find **August Local** in HACS and install
6. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Extract to `~/.homeassistant/custom_components/august_local/`
3. Restart Home Assistant

## Setup

### Account-assisted wizard

August Local requires the official [HA August integration](https://www.home-assistant.io/integrations/august/) to be loaded and signed in before the wizard can continue. If it is not present, [add it here](https://my.home-assistant.io/redirect/config_flow_start?domain=august) and complete its supported authentication, then return to August Local setup.

1. **Settings → Devices & Services → Add Integration** → search **August Local**
2. If no signed-in August account is loaded, the guidance step opens; complete official August setup and press **Submit** to check again. Otherwise, the account chooser opens directly
3. Under **Choose your connected August account**, select the loaded account
4. Select the lock registered to that account
5. Confirm BLE key validation — the wizard connects to the lock locally and validates its installed key without moving the deadbolt
6. Setup completes; Door PINs panel appears in the sidebar

No password is entered or stored by August Local. Account errors direct to the official August integration; account errors and Bluetooth errors are separate. For an existing Door PINs installation, use **Configure → Reconnect account and Bluetooth key**. Selecting another lock is rejected before Bluetooth validation.

### Updating after a rejected password login

Update August Local to 0.10.7 or newer in HACS and restart Home Assistant to load the replacement flow. Dismiss any unfinished old August Local password form and start setup again. Add and sign in through the official **August** integration first; it is separate from **August Local**. Existing Door PINs entries and Yale Access Bluetooth credentials do not need deleting or resetting. Keep the lock's current ownership and keys intact.

## Usage

### Automatic PIN slots

Use **Provision PIN capacity** instead of choosing slot numbers. Automatic mode reserves one slot per active personal HA user; count mode requests a total capacity for additional manually created PINs. Provisioning reads local slot occupancy and allocates only slots the lock positively reports empty; the one exception is capacity growth following a successfully confirmed explicit global clear (initialized state, exclusive mode, consumed one-use authorization, initialized receipt), which allocates only slots with no existing HA record, preserves all existing, uncertain, and imported records, and issues no further clear or occupancy read. It does not create PINs, clear existing codes or use cloud-list omissions as evidence that a slot is free. An unsupported read or timeout stops discovery rather than trying writes against unknown slots. Existing HA-created PINs remain recorded; old unchecked range reservations are not evidence of empty slots.

Use **Add PIN** to enter a code after capacity has been discovered. The lock's command acknowledgement is shown as **programmed, unverified**, not proof that the physical keypad accepts it. Confirm keypad pairing and test the code physically only when unlocking is safe. A working auto-lock setting does not verify keypad programming.

Capacity requests expand or reuse the existing HA allocation; requesting a smaller number does not delete PINs or take slots away from other users. Provisioning assigns slots, not generated PIN values. Firmware support must be confirmed on the actual lock; there is no fallback that guesses free slots.

### Read-only slot diagnostics

In **Advanced PIN setup → Read slot occupancy**, enter a slot to inspect. This administrator-only check does not reserve it or write a test code. A successful status read precedes the occupancy command; after a failed occupancy read another status read checks whether the link still responds. Diagnostics retain only safe codes, response length, slot-echo validity, acknowledgement presence and opcode numbers—not PINs or decrypted frames. A timeout is not a statement about capacity or proof that firmware lacks the command.

### HA-only initialization — last resort

Prefer importing an existing August code or updating an existing HA-managed slot before using this option. **Advanced PIN setup → HA-only initialization (last resort)** erases every keypad code on this configured lock, including codes created outside HA. Keep an alternative way to enter. This is an experimental ASL-05-only command path. Physical testing on ASL-05 firmware 1.1.30 with keypad 2.27.0 confirmed: after explicitly authorized HA-only initialization, a previously registered code was rejected at the keypad and a newly programmed HA-managed code was accepted. Command acknowledgement alone is not physical evidence; this result applies only to that tested hardware and does not establish arbitrary unknown-slot discovery, support for other firmware versions, total hardware capacity, native schedules, or keypad commissioning.

Select automatic capacity (one per active personal HA user) or a chosen total from 1–50, then type **ERASE ALL KEYPAD CODES**. This is a separate action, never an automatic response to failed discovery. No PINs are generated. Only a confirmed clear-all response prepares HA-cleared slots; use **Add PIN** afterwards and physically verify acceptance when safe. The chosen total is an HA allocation, not a measured hardware capacity.

Initialization journals and consumes a one-use authorization before sending the command. Repeated submissions with the same operation ID do not issue another clear. An interrupted or unconfirmed attempt retains prior credentials as recovery evidence, invalidates empty-slot claims and does not automatically retry. Reopening and confirming another initialization is a new destructive decision, not recovery by guessing. Do not use the August app or another integration to write any keypad code on the lock afterwards — not merely the currently allocated range: future capacity growth depends on the entire cleared baseline remaining exclusive to HA. Reading the August account cloud inventory is not prohibited.

This action does not factory-reset the lock, revoke keys, change ownership, unpair the keypad or move the deadbolt. It is not required to replace a retained, working HA PIN. The underlying guarded service cannot bypass the panel's manager authorization with a standalone call.

Local clearing does not delete August's cloud PIN records. Official-app Bluetooth synchronization may restore those codes or reuse slots; avoid such synchronization after initialization. Read-only cloud API inventory does not itself write codes.

### Existing HA slot: change, re-add or recover

Changing a retained PIN uses the original known-PIN clear/set/schedule/commit transaction, not automatic discovery. After an acknowledged deletion, **Add PIN** can reuse that same HA-managed slot without relying on an occupancy read. Keep the slot exclusive to HA; do not separately reuse it in the August app. The clear proof is consumed and saved before insertion, and an interrupted insertion cannot reuse it after a restart.

For **Needs recovery**, use **Recover / replace slot** and explicitly confirm clearing its retained HA-created candidates. Enter a replacement PIN. Only that slot's retained candidates are cleared; every clear must succeed before insertion. Unknown, imported and other users' slots cannot use this recovery route.

Older failed preflight handling may have discarded the candidate and left an unverified reservation. An administrator can use **Restore known HA slot** for that existing record, enter its last known HA-created PIN and a replacement, and confirm that this slot was dedicated to HA. This is an explicit known-code operation, not a claim that the slot is empty. If the known-code clear is rejected or unconfirmed, recovery stops and sends no replacement. Without the last known code, there is no safe automatic restoration of lost evidence.

### Door PINs Panel

Open Home Assistant sidebar → **Door PINs** to:
- Create new access codes (you own the slot)
- Assign codes to specific HA users
- Delete codes
- Read/set the lock's native auto-lock timer
- Configure arrival-based auto-unlock

### Auto-Unlock

1. Ensure **HA Companion app** is installed on your phone
2. Go to **Door PINs** panel → **Arrival Unlock**
3. Use **1. Phone proximity** to configure and test the door receiver and threshold
4. Use **2. Arrival automation** to select the home entity and fresh nearby-phone sensor
5. Create the automation, review it, and explicitly enable it. New automations start disabled

Arrival requires an observed departure from home, continuously known-away location for the configured minimum time, and a subsequent return home. A template trigger measures continuous absence; forced GPS reports can reset `last_changed`, so timestamp subtraction is not reliable for this purpose. Moving between named away zones does not reset the minimum period. Enabling, reloading or restarting while already away does not arm unlocking: a new complete home/departure/return cycle is required. An unknown or unavailable location invalidates eligibility, and every new departure immediately cancels any previous proximity wait, even for a short trip.

The automation waits up to 30 minutes for matching door-proxy proximity. Proximity detection uses a decay accumulator requiring at least three strong samples spanning two seconds, accommodating background BLE packet intervals. Before unlocking it checks that the phone remains home, proximity is fresh (<10s old and no earlier than arrival), and the deadbolt is locked. If the door was already unlocked when approaching, the unlock action is safely skipped. Calibrate the RSSI threshold with the phone actually by the door; do not lower it merely to force a test to pass. BLE beacons are not authenticated credentials, and location accuracy still matters.

These guards apply to newly generated automations. Existing saved automations are not silently overwritten by an integration update; review and update their configuration separately. A controlled test with an isolated temporary tracker can verify arrival processing and the real Bluetooth/lock path without changing the phone's GPS, but cannot prove real location updates or background tracking. Keep physical unlock tests separately authorized and remove temporary test entities afterwards.

### Service calls

Service domain: `august_local`

- `august_local.program` — add or change a PIN in an owned slot
- `august_local.insert` — recheck an owned slot is empty before inserting a PIN
- `august_local.delete` — delete a PIN
- `august_local.status` — check lock status

See the action developer tool in Home Assistant and `custom_components/august_local/services.yaml` for parameter details.

## Architecture

This integration:
- Operates on top of **Yale Access Bluetooth** (`yalexs_ble`) for BLE transport
- Uses an August account once during setup to import the lock's installed offline key
- Stores the validated BLE key and slot via `yalexs_ble` in HA config
- Does not contact August cloud for day-to-day PIN or auto-lock operations
- Uses the August BLE protocol for PIN commands
- Never logs PIN contents or decrypted BLE frames

**Note:** Local BLE control does not guarantee the lock's WiFi module never contacts August's cloud. The official August integration may independently refresh its OAuth session and contact August's servers.

## Security notes

- **Offline key**: stored by `yalexs_ble` in Home Assistant configuration — protect HA config secrets
- **PINs**: never logged, traced, or exposed to HA entity states/recorder/automations
- **PIN slots**: non-admin users can only manage PINs in their assigned slots
- **Admin users**: can manage all slots and settings
- **August account**: August Local borrows access from the official integration and never stores or logs the token or password; account errors direct to the official integration

## Known limitations

- **Factory-reset locks**: registering a new lock or installing a new offline credential is not yet supported; use the August app to provision the lock first
- **Keypad pairing**: requires the August Smart Keypad to already be paired via the official app; HA-side pairing is not implemented
- **PIN readback**: reliable enumeration is not established for the tested ASL-05 firmware — only imported or locally managed records are tracked
- **PIN schedules**: day/time enforcement is not implemented. Use the August app; HA timer-based deletion/reinsertion is not a safe substitute when HA or Bluetooth is offline. Restricted imported PINs cannot be locally replaced with always-access codes
- **One instance per HA**: only one Door PINs entry per HA instance
- **BLE key rotation**: if `yalexs_ble` prompts for re-authentication, re-run the account wizard (Configure → Reconnect account and Bluetooth key); see [upstream guidance](https://www.home-assistant.io/integrations/yalexs_ble/#lock-frequently-requires-re-authentication)

## Troubleshooting

### Account error during setup

Open the [official HA August integration](https://my.home-assistant.io/redirect/integrations/?domain=august) and verify it is loaded and signed in. Account errors are separate from Bluetooth errors; do not retry the August Local wizard until the official integration reports a healthy account. Repeated sign-in attempts can trigger rate limits on August's side.

### "No offline key"

The selected lock has no installed offline key available to this account. The lock must be registered and have its offline key provisioned via the August app before it can be imported here.

### BLE key validation fails

- Keep the Bluetooth proxy near the lock
- Close the August app on any nearby phone (it may hold the BLE connection)
- Retry; if it persists, the lock's offline key may need refreshing via the August app

### PIN operations fail ("outcome unknown")

- **Disconnected during discovery:** a Bluetooth disconnect while reading occupancy is unknown, not an empty slot. Version 0.10.10 handles the upstream `DisconnectedError` explicitly instead of returning an internal filename/line error. Discovery sends no PIN-changing command; keep unknown slots unavailable
- During a request, the panel shows a spinner, marks itself busy and disables PIN controls. Bluetooth can take over a minute. Do not submit the operation again or treat a slow response as proof of failure
- In 0.10.9, a known occupancy preflight block reports that no new PIN was sent rather than labelling it as an uncertain write. Occupancy must still be verified before another insertion
- **Needs recovery** means the operation's outcome is unconfirmed, not that the PIN is definitely invalid. Previously uncertain records and retained PIN values are not automatically cleared by an update
- If a write completes but refreshing the panel fails, the panel distinguishes the refresh failure and never automatically repeats the write
- A timeout does not prove whether a write was applied; do not retry blindly
- Inspect the recorded failure stage and the manager's needs-attention state before any separately authorized recovery
- Check HA logs for the failure stage name and exception type

### Opening lock settings

- Auto-lock settings open immediately in a Home Assistant card with a progress indicator while reading Bluetooth. Repeated clicks reuse the open editor and in-flight read; closing or switching settings prevents a late response from reopening an old menu
- Arrival settings are local UI and open without a Bluetooth request. They remain separate from actually enabling automatic unlocking

### Auto-unlock not working

- Companion app must be running with Bluetooth enabled
- Allow precise location all the time and unrestricted background battery usage; enable Background location, Location zone and Single accurate location
- Check Companion app troubleshooting → Location tracking for failed deliveries, and confirm HA actually records departure and return
- Check that your home zone is correctly configured in HA
- Verify the BLE proxy is within range
- Check that automations were created in Home Assistant
- Check that the arrival automation is enabled and the phone was actually away for the configured minimum time
- After enabling or reloading, begin a new departure from home; an already-away phone intentionally cannot arm unlocking
- Verify the near-door sensor turns on with fresh samples at the door; a transmitting phone can still be below the calibrated RSSI threshold
- Do not use an automation's manual Run button as proof of arrival: it may skip trigger conditions or lack the required state-trigger context

## Support

For issues, questions, or feature requests: [GitHub Issues](https://github.com/websterwh/august-local-hacs/issues)

## License

MIT License — not affiliated with August Home Inc. or Yale.
