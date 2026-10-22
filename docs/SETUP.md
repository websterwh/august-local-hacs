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

Use **Provision PIN capacity** instead of choosing slot numbers. Automatic mode reserves one slot per active personal HA user; count mode requests a total capacity for additional manually created PINs. Provisioning reads local slot occupancy and allocates only slots the lock positively reports empty. It does not create PINs, clear existing codes or use cloud-list omissions as evidence that a slot is free. An unsupported read or timeout stops discovery rather than trying writes against unknown slots. Existing HA-created PINs remain recorded; old unchecked range reservations are not evidence of empty slots.

Use **Add PIN** to enter a code after capacity has been discovered. The lock's command acknowledgement is shown as **programmed, unverified**, not proof that the physical keypad accepts it. Confirm keypad pairing and test the code physically only when unlocking is safe. A working auto-lock setting does not verify keypad programming.

Capacity requests expand or reuse the existing HA allocation; requesting a smaller number does not delete PINs or take slots away from other users. Provisioning assigns slots, not generated PIN values. Firmware support must be confirmed on the actual lock; there is no fallback that guesses free slots.

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

- A timeout does not prove whether a write was applied; do not retry blindly
- Inspect the recorded failure stage and the manager's needs-attention state before any separately authorized recovery
- Check HA logs for the failure stage name and exception type

### Auto-unlock not working

- Companion app must be running with Bluetooth enabled
- Check that your home zone is correctly configured in HA
- Verify the BLE proxy is within range
- Check that automations were created in Home Assistant

## Support

For issues, questions, or feature requests: [GitHub Issues](https://github.com/websterwh/august-local-hacs/issues)

## License

MIT License — not affiliated with August Home Inc. or Yale.
