# August Local Keypad - Complete Setup Guide

## What This Integration Does

**August Local Keypad** adds complete PIN/keypad management, auto-lock control, and location-based auto-unlock to Home Assistant for **factory-reset August ASL-05 locks** — with **zero cloud contact after setup**.

Features:
- ✅ **Factory-reset enrollment** - Set up a blank lock entirely via Bluetooth, no August app needed
- ✅ **PIN management** - Add/change/delete codes directly from HA, per-user access control
- ✅ **Auto-lock** - Timer-based automatic locking (stored on the lock, works offline)
- ✅ **Auto-unlock** - Location + Bluetooth beacon proximity-based arrival unlock
- ✅ **Keypad pairing** - Pair/unpair August Smart Keypads
- ✅ **Multi-user** - Non-admin HA users manage only their own PINs

## Prerequisites

1. **Home Assistant** 2024.1 or later
2. **Bluetooth adapter** or **ESPHome Bluetooth proxy** within range of the lock
3. **Factory-reset August ASL-05 lock** ready for enrollment (not previously paired to any August account)
4. **HACS** installed (for easy updates)

## Installation

### Via HACS (Recommended)

1. Open Home Assistant → **Settings → Devices & Services → Integrations**
2. Click **⋮ → Custom repositories**
3. Add: `https://github.com/websterwh/august-local-hacs`
4. Category: **Integration**
5. Find **August Local Keypad** in HACS and install
6. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Extract to `~/.homeassistant/custom_components/august_local_keypad/`
3. Restart Home Assistant

## Setup

### Option 1: Enroll a Factory-Reset Lock (Recommended)

**This option requires a factory-reset lock with no previous August account.**

1. Factory-reset your lock:
   - Hold the physical reset button on the lock for 30+ seconds
   - Watch for LED to flash, then stop flashing (wait for silence)
   - Keep holding another 10 seconds to ensure factory-reset mode is active

2. In Home Assistant: **Settings → Devices & Services → Add Integration**

3. Search for **August Local Keypad** and select **Enroll a Factory-Reset Lock**

4. Enter your lock's **Bluetooth MAC address** (e.g., `78:9C:85:33:F8:34`)
   - Find it by scanning nearby BLE devices in Home Assistant's Bluetooth settings, or
   - Check the lock's label, or
   - Use a BLE scanner app on your phone

5. The integration will:
   - Discover the lock
   - Trigger enrollment mode
   - Capture enrollment nonces from BLE advertisements
   - Derive a secure session key
   - Generate and write an offline key to the lock
   - Complete setup

6. When done, the lock is ready to use — **no cloud account needed**

### Option 2: Use an Existing Yale Access Bluetooth Entry

If you already have the **Yale Access Bluetooth** integration set up with a lock:

1. Add Integration → **August Local Keypad** → **Use an Existing Bluetooth Lock**
2. Select the lock from your existing Yale Access Bluetooth entries
3. Done — the lock key is imported automatically

### Option 3: Import from August Account (Rare)

If you have an August account already synced with this lock in Home Assistant:

1. Add Integration → **August Local Keypad** → **Use August Account**
2. Select your August account and then the specific lock
3. The key is imported; cloud is no longer used for that lock

## Usage

### Door PINs Panel

Open Home Assistant sidebar → **Door PINs** to:
- Create new access codes (you own the slot)
- Assign codes to specific HA users
- Set expiration dates and schedules
- Delete codes
- Read/set the lock's native auto-lock timer
- Configure arrival-based auto-unlock

### Auto-Unlock

1. Ensure **HA Companion app** is installed on your phone
2. Go to **Door PINs** panel → **Arrival Unlock**
3. Configure:
   - **Proximity threshold** (Bluetooth beacon range)
   - **Home entity** (zone where you live)
   - Enable/disable for specific users
4. Automations are created automatically; you can customize them

### Manual Commands

Service calls available:
- `august_local_keypad.program` - Add/change a PIN
- `august_local_keypad.delete` - Delete a PIN
- `august_local_keypad.status` - Check lock status

See **Services** in Home Assistant for full details.

## Troubleshooting

### Enrollment Fails ("Lock not found")

- **Lock not in factory-reset mode**: Hold button another 10-30 seconds, lock should accept BLE writes
- **Too far away**: Move lock closer to Bluetooth adapter
- **Bluetooth adapter disabled**: Check Home Assistant Bluetooth integration is running
- **Lock has a key installed**: Factory-reset again (harder/longer button press)

### "Invalid MAC address"

Format must be `XX:XX:XX:XX:XX:XX` (6 pairs of hex digits separated by colons)

### PIN operations fail ("outcome unknown")

- Normal if lock goes offline mid-operation (timeouts are safe)
- Retry the operation — the lock will reject duplicate writes if the slot is already set
- Check HA logs for exact error

### Auto-unlock not working

- Companion app must be running with Bluetooth enabled
- Check that your home zone is correctly configured in HA
- Verify BLE beacon proximity is within range
- Check automations in Home Assistant were created correctly

## Architecture

This integration:
- Operates on top of **Yale Access Bluetooth** (`yalexs_ble`) for BLE transport
- Never contacts August cloud servers for day-to-day operation
- Stores the offline key locally in HA (encrypted in config)
- Uses real Yale/August BLE protocol (reverse-engineered from captured traffic)
- Manages PINs via legacy ASL-05 commands (0x28, 0x2B, 0x2C opcodes)
- Never logs PIN contents or decrypted BLE frames

## Security Notes

- **Offline key**: Stored in Home Assistant configuration (protected by HA security)
- **PINs**: Never logged, traced, or exposed to HA entity states/recorder/automations
- **PIN slots**: Non-admin users can only manage PINs in their assigned slots
- **Admin users**: Can manage all slots and settings
- **Factory-reset**: Erases all keys and settings on the lock

## Known Limitations

- **PIN readback**: ASL-05 firmware 1.1.30 does not support reading existing PINs — only codes written by this integration are tracked
- **Keypad pairing**: Requires the lock to already have the physical August Smart Keypad installed
- **Factory-reset only**: Only works with locks that have never been enrolled to an August account (or after factory-reset)
- **One integration per lock**: Only one HA instance can control a given lock key

## Support

For issues, questions, or feature requests: [GitHub Issues](https://github.com/websterwh/august-local-hacs/issues)

## License

MIT License — not affiliated with August Home Inc. or Yale.
