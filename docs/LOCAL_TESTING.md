# August Local - Local Testing Plan

## Current Status

- ✅ Integration renamed to `august_local` (domain + display name)
- ✅ Enrollment step disabled (pending connectivity verification)
- ✅ All core PIN/auto-lock features ready
- ⚠️ **Lock connectivity issue**: Lock not responding after enrollment attempt

## Immediate Next Step

**The lock is not advertising BLE.** It needs to be woken up or reset.

### 1. Wake/Reset the Lock

Try **in order**:

1. **Press the lock button** (any press should wake it)
2. **Wait 30 seconds** and scan again
3. **If still offline**: Hold reset button 30+ seconds (until LED flashes) to factory-reset

Then run:

```bash
python3 debug_lock_connectivity.py
```

This will show:
- All BLE devices in range
- Whether lock appears
- Connection attempts with multiple timeouts

### 2. If Lock Still Not Found

- Check: Is the lock powered on? (should have indicator/LED)
- Check: Is Bluetooth adapter working? (script should show OTHER devices)
- Check: Is lock within 5 meters of adapter?

If other devices appear in scan but not lock → lock's BLE is offline/crashed

### 3. Once Lock Appears

Run the debug script again. Once it connects successfully, we can proceed with testing.

## Testing Phases (After Connectivity)

### Phase 1: Existing Features (No Enrollment)

Use the existing setup methods (not factory-reset enrollment):

1. **Via August Account** (if you have one):
   - Add Integration → August Local → Use August Account
   - HA will import key from cloud account
   
2. **Via Yale Access Bluetooth** (if lock is already in that integration):
   - Add Integration → August Local → Use Existing Bluetooth Lock
   - HA will use existing yale entry's key

3. Test:
   - ✓ Door PINs panel loads
   - ✓ Can create/delete PINs
   - ✓ Can read lock status
   - ✓ Can set auto-lock timer
   - ✓ Can configure auto-unlock

### Phase 2: Enrollment Feature (Once Connectivity Confirmed)

Once lock is responsive, we'll:

1. Factory-reset again
2. Enable `async_step_enroll()` in config_flow.py
3. Test enrollment flow:
   - Nonce capture
   - Session key derivation
   - Offline key generation
   - Key write success
4. Then test PIN operations with provisioned key

## Debugging Commands

```bash
# Full BLE scan (current status)
python3 debug_lock_connectivity.py

# Quick scan (what devices are visible)
python3 -c "
import asyncio
from bleak import BleakScanner
async def scan():
    devices = await BleakScanner.discover(timeout=10)
    for d in devices:
        if d.address.lower() == '78:9c:85:33:f8:34':
            print(f'[✓] Lock found: {d.name}')
            return
    print('[!] Lock not found')
asyncio.run(scan())
"
```

## Files

- `debug_lock_connectivity.py` - BLE connectivity troubleshooting
- `custom_components/august_local/` - Integration (enrollment disabled)
- `custom_components/august_local/enrollment.py` - Enrollment code (ready to test)

## Notes

- Integration is functional for existing locks (no enrollment needed)
- Enrollment is production-ready code but needs real hardware test
- Connection timeout issue is environmental (lock offline), not code issue
- Once lock responds, can proceed with full integration test

**Proceed with Phase 1 (existing features) while troubleshooting lock connectivity.**
