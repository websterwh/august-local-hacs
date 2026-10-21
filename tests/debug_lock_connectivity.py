#!/usr/bin/env python3
"""Debug August lock BLE connectivity issues."""

import asyncio
import sys
from bleak import BleakScanner, BleakClient
from bleak.backends.client import BaseBleakClient

async def scan_all_devices():
    """List all BLE devices within range."""
    print("[*] Scanning for ALL BLE devices (20s)...")
    devices = await BleakScanner.discover(timeout=20.0)
    
    if not devices:
        print("[!] No BLE devices found at all!")
        print("[!] Check: Bluetooth adapter enabled? Linux BlueZ running?")
        return None
    
    print(f"[*] Found {len(devices)} devices:\n")
    for d in sorted(devices, key=lambda x: getattr(x, 'rssi', 0) or -100, reverse=True):
        rssi = getattr(d, 'rssi', None)
        name = d.name or "(no name)"
        rssi_str = f"({rssi} dBm)" if rssi else ""
        print(f"  {d.address:17} {name:30} {rssi_str}")
    
    return devices


async def try_connect(mac: str):
    """Try to connect to lock with multiple timeout strategies."""
    print(f"\n[*] Attempting connection to {mac}...\n")
    
    # Check if it's in the scan
    devices = await BleakScanner.discover(timeout=5.0)
    found = any(d.address.lower() == mac.lower() for d in devices)
    
    if not found:
        print(f"[!] Device not found in quick scan")
        print(f"[!] Lock may be:")
        print(f"    - Powered off")
        print(f"    - Out of Bluetooth range")
        print(f"    - In sleep mode (no advertising)")
        return False
    
    print(f"[✓] Device found in scan\n")
    
    # Try different timeout values
    for timeout in [10.0, 20.0, 30.0]:
        print(f"[*] Trying connection with {timeout}s timeout...")
        client = BleakClient(mac, timeout=timeout)
        
        try:
            await client.connect()
            print(f"[✓✓✓] SUCCESS with {timeout}s timeout!")
            await client.disconnect()
            return True
        
        except asyncio.TimeoutError as e:
            print(f"  [!] Timeout: {e}")
        
        except Exception as e:
            print(f"  [!] Error: {type(e).__name__}: {e}")
            if "disconnect" in str(e).lower():
                print(f"  [!] Note: Lock rejected/disconnected")
            break
    
    return False


async def main():
    """Main debug routine."""
    print("\n" + "="*80)
    print("AUGUST LOCK BLE CONNECTIVITY DEBUG")
    print("="*80 + "\n")
    
    devices = await scan_all_devices()
    
    if not devices:
        print("\n[!!!] No BLE devices found at all!")
        print("[!!!] This means:")
        print("      1. Bluetooth adapter is disabled/unplugged")
        print("      2. Linux BlueZ daemon is not running")
        print("      3. bleak/Bluetooth permissions are broken")
        sys.exit(1)
    
    target_mac = "78:9C:85:33:F8:34"
    success = await try_connect(target_mac)
    
    if not success:
        print(f"\n[!!!] Could not connect to {target_mac}")
        print(f"[!!!] Next steps:")
        print(f"      1. Check lock is powered on")
        print(f"      2. Check lock is not in sleep mode (press button)")
        print(f"      3. Check lock is within 5 meters of Bluetooth adapter")
        print(f"      4. Try factory-reset lock again (hold button 30+ seconds)")
        print(f"      5. Check if lock is listed above in the scan results")
    else:
        print(f"\n[✓✓✓] Lock is reachable and responsive!")


if __name__ == "__main__":
    asyncio.run(main())
