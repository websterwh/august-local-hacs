# Bootstrap Enrollment: One-Time August Account Setup

## Problem
Factory-reset August ASL-05 locks have no installed encryption key. The lock requires initial authentication via August's servers to receive and store a handshake key. After that, the lock operates entirely offline.

## Solution: One-Time August Account

**You need to use an August account exactly once.** After bootstrap, the lock's key is permanently installed and you can delete your account. Future connections are 100% local.

### Timeline
1. Create/use August account: **5 minutes**
2. Add lock via August app: **10 minutes** (lock receives key)
3. Delete account: **2 minutes**
4. Switch to HA offline control: **Permanent**

### Steps

#### 1. Create August Account (or use existing)
- **Option A:** Create free account at https://account.august.com
  - Email + password, no payment required
  - Temporary; you'll delete it after setup

- **Option B:** Use existing August account
  - If you have one, use it; no new account needed

#### 2. Add Lock via August App
- **Install August app** on iOS or Android
- **Sign in** with your account
- **Select "Add Lock"** or **"Add Device"**
- **Choose "August Smart Lock"** (ASL-05)
- **Select your lock's MAC address** from Bluetooth scan (look for `78:9C:85:33:F8:34`)
- **Wait for commissioning** (app will show "Processing...")

**What happens behind the scenes:**
1. App sends `POST /locks/initiatecomm/{lockId}` with two random numbers
2. August server generates a 16-byte encryption key
3. Server encrypts the key and sends it to the lock via Bluetooth
4. Lock stores the key in firmware (permanent, survives power loss and factory reset)

#### 3. Verify Lock Setup
- August app should show lock status as **"Online"** or **"Connected"**
- Lock's LED should flash (indicates successful key receipt)

#### 4. Delete Account (Optional but Recommended)
- Go to August account settings
- Select **"Delete Account"**
- Confirm (data deleted, no recovery)

The lock **retains its key** and continues working even after the account is deleted.

#### 5. Switch to Home Assistant Offline

Once the lock is keyed:

1. **In HA**, add the "August Local" integration
2. **Select "Use an existing HA Bluetooth lock"**
3. **Choose your lock** from the Yale Access Bluetooth integration list
4. **No cloud contact after this point**—lock operates entirely locally

## Why This is Necessary

The August ASL-05 protocol requires a bootstrap key exchange with August's servers because:

1. **The lock has a secret key burned into firmware during manufacturing**
2. **That key is never transmitted; only used for decryption**
3. **August's servers use that key to encrypt the handshake packet**
4. **Without the encrypted packet, the lock cannot install a working key**

Cloud-free enrollment is **not possible** without either:
- Hardware access to extract the firmware's secret (requires JTAG/chip-off)
- Capturing the encrypted packet from August's servers (requires network MITM + reverse engineering)
- Public disclosure of the secret key (has not occurred)

## After Bootstrap: 100% Offline Operation

Once the key is installed, your lock:

✅ Never contacts August servers  
✅ Never needs an internet connection  
✅ Works with local HA Bluetooth only  
✅ Supports keypad PINs, auto-lock, arrival automation  
✅ Survives account deletion  
✅ Persists through factory resets (key does not clear)

## Troubleshooting

### Lock Not Appearing in August App
- Ensure lock is powered (press button)
- Ensure lock is in Bluetooth range (within 10m)
- Restart the August app

### "Lock Not Responding" During Commissioning
- Keep app and lock in close proximity (< 5m)
- Check that Bluetooth is enabled on phone
- Try again after 30 seconds

### Lock Still Not Working After HA Setup
- Restart Home Assistant
- Check HA Bluetooth proxy is running
- Verify MAC address matches: `78:9C:85:33:F8:34`

## References

- [August Smart Lock Support](https://support.august.com)
- [HA Bluetooth Integration](https://www.home-assistant.io/integrations/bluetooth)
- [Yale Access Bluetooth Integration](https://www.home-assistant.io/integrations/yalexs_ble)
