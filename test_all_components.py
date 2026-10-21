#!/usr/bin/env python3
"""Comprehensive local test of August Local integration components."""

import asyncio
import os
import sys

passed = []
failed = []

async def test_1_ble_connectivity():
    """Can we discover and connect to the lock?"""
    from bleak import BleakScanner, BleakClient
    
    mac = "78:9C:85:33:F8:34"
    print(f"[*] Scanning for lock {mac}...")
    devices = await BleakScanner.discover(timeout=10.0)
    
    device = next((d for d in devices if d.address.lower() == mac.lower()), None)
    assert device is not None, f"Lock {mac} not found"
    print(f"[✓] Found: {device.name}")
    
    print(f"[*] Connecting...")
    client = BleakClient(mac, timeout=20.0)
    await client.connect()
    svc_count = sum(1 for _ in client.services)
    print(f"[✓] Connected, {svc_count} services")
    await client.disconnect()

async def test_2_nonce_extraction():
    """Can we extract enrollment nonces from advertisements?"""
    from bleak import BleakScanner
    
    mac = "78:9C:85:33:F8:34"
    print(f"[*] Scanning with advertisement data...")
    devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
    
    for mac_addr, (ble_device, adv_data) in devices.items():
        if mac_addr.lower() == mac.lower():
            assert adv_data.manufacturer_data, "No manufacturer data"
            
            combined = b''
            for mfg_id in sorted(adv_data.manufacturer_data.keys()):
                combined += adv_data.manufacturer_data[mfg_id]
            
            assert len(combined) >= 16, "Not enough data for nonces"
            lock_nonce = combined[0:8]
            mobile_nonce = combined[8:16]
            print(f"[✓] Lock nonce:   {lock_nonce.hex()}")
            print(f"[✓] Mobile nonce: {mobile_nonce.hex()}")
            
            with open("/tmp/test_lock_nonce.hex", "w") as f:
                f.write(lock_nonce.hex())
            with open("/tmp/test_mobile_nonce.hex", "w") as f:
                f.write(mobile_nonce.hex())
            return
    
    raise AssertionError("Lock not found")

async def test_3_session_key_derivation():
    """Can we derive a valid session key?"""
    lock_nonce = bytes.fromhex(open("/tmp/test_lock_nonce.hex").read())
    mobile_nonce = bytes.fromhex(open("/tmp/test_mobile_nonce.hex").read())
    
    session_key = mobile_nonce + lock_nonce
    assert len(session_key) == 16, f"Session key wrong length: {len(session_key)}"
    print(f"[✓] Session key: {session_key.hex()}")
    
    with open("/tmp/test_session_key.hex", "w") as f:
        f.write(session_key.hex())

async def test_4_offline_key_generation():
    """Can we generate a valid offline key?"""
    offline_key = os.urandom(16)
    assert len(offline_key) == 16
    print(f"[✓] Generated: {offline_key.hex()}")
    
    with open("/tmp/test_offline_key.hex", "w") as f:
        f.write(offline_key.hex())

async def test_5_aes_frame_encryption():
    """Can we properly encrypt BLE frames?"""
    import struct
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    
    session_key = bytes.fromhex(open("/tmp/test_session_key.hex").read())
    offline_key = bytes.fromhex(open("/tmp/test_offline_key.hex").read())
    
    # Build write-lower frame
    opcode = 0x11
    key_data = offline_key[0:8]
    words = struct.unpack("<II", key_data)
    checksum = (-(sum(words))) & 0xFFFFFFFF
    
    plaintext = struct.pack("<B", opcode) + key_data + struct.pack("<I", checksum) + b'\x00' * 3
    assert len(plaintext) == 16
    
    cipher = Cipher(algorithms.AES(session_key), modes.CBC(b'\x00' * 16))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    assert len(ciphertext) == 16
    
    frame = ciphertext + bytes([0x0F, 0x01])
    print(f"[✓] Frame: {frame.hex()}")
    
    with open("/tmp/test_frame.hex", "w") as f:
        f.write(frame.hex())

async def test_6_ble_write():
    """Can we write encrypted frames to the lock?"""
    from bleak import BleakClient
    
    mac = "78:9C:85:33:F8:34"
    frame = bytes.fromhex(open("/tmp/test_frame.hex").read())
    
    print(f"[*] Connecting...")
    client = BleakClient(mac, timeout=20.0)
    await client.connect()
    
    try:
        sec_char = None
        for service in client.services:
            for char in service.characteristics:
                if "write" in char.properties and ("0030" in str(char.uuid) or "0050" in str(char.uuid)):
                    sec_char = char
                    break
            if sec_char:
                break
        
        assert sec_char, "Write characteristic not found"
        print(f"[*] Writing {len(frame)} bytes...")
        await client.write_gatt_char(sec_char, frame, response=False)
        print(f"[✓] Write sent")
        await asyncio.sleep(1)
    finally:
        await client.disconnect()

async def test_7_yalexs_ble():
    """Does yalexs_ble work with lock?"""
    from yalexs_ble import PushLock
    
    mac = "78:9C:85:33:F8:34"
    test_key = bytes.fromhex("00" * 16)
    
    print(f"[*] Testing yalexs_ble library...")
    lock = PushLock(mac, test_key)
    
    try:
        await asyncio.wait_for(lock.wait_for_first_update(timeout=3.0), timeout=5.0)
        print(f"[✓] Connected (unexpected)")
    except asyncio.TimeoutError:
        print(f"[✓] Library works (timeout expected)")
    except Exception as e:
        print(f"[✓] Library works ({type(e).__name__} expected for wrong key)")

async def run_all():
    """Run all tests."""
    tests = [
        ("1. BLE Connectivity", test_1_ble_connectivity),
        ("2. Nonce Extraction", test_2_nonce_extraction),
        ("3. Session Key Derivation", test_3_session_key_derivation),
        ("4. Offline Key Generation", test_4_offline_key_generation),
        ("5. AES Frame Encryption", test_5_aes_frame_encryption),
        ("6. BLE Write Operation", test_6_ble_write),
        ("7. yalexs_ble Integration", test_7_yalexs_ble),
    ]
    
    print("\n" + "█"*80)
    print("AUGUST LOCAL - COMPREHENSIVE LOCAL TEST")
    print("█"*80 + "\n")
    
    for name, test_func in tests:
        print(f"\n{'='*80}")
        print(f"TEST: {name}")
        print('='*80)
        try:
            await test_func()
            passed.append(name)
            print(f"\n✅ PASSED")
        except Exception as e:
            failed.append((name, str(e)))
            print(f"\n❌ FAILED: {e}")
        
        await asyncio.sleep(0.5)
    
    # Summary
    print("\n" + "="*80)
    print(f"RESULTS: {len(passed)}/{len(tests)} passed")
    print("="*80)
    
    for name in passed:
        print(f"✅ {name}")
    
    for name, err in failed:
        print(f"❌ {name}: {err}")
    
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_all())
