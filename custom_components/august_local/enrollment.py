"""Factory-reset August ASL-05 enrollment and key provisioning.

Captures enrollment nonces, derives session key, and writes offline key
to the lock for permanent cloud-free control.
"""

import asyncio
import os
import struct
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from bleak import BleakClient, BleakScanner


class EnrollmentError(Exception):
    """Enrollment failed."""


class ASL05Enrollment:
    """Enroll a factory-reset August ASL-05 lock."""
    
    def __init__(self, lock_mac: str, slot: int = 1, *, device=None):
        self.lock_mac = lock_mac
        self.slot = slot
        self.device = device
        self.client = None
        self.nonces = None
        self.session_key = None
        self.offline_key = None
    
    async def discover_lock(self, timeout: int = 180) -> bool:
        """Wait for lock to appear in BLE scan."""
        if self.device is not None:
            return True
        print(f"[*] Waiting for lock {self.lock_mac} ({timeout}s timeout)...")
        start = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start < timeout:
            try:
                devices = await BleakScanner.discover(timeout=5.0)
                for d in devices:
                    if d.address.lower() == self.lock_mac.lower():
                        self.device = d
                        print(f"[✓] Found: {d.name}")
                        return True
                
                elapsed = int(asyncio.get_event_loop().time() - start)
                if elapsed % 30 == 0 and elapsed > 0:
                    print(f"  [{elapsed}s] Still waiting...")
            
            except Exception as e:
                print(f"[!] Scan error: {e}")
            
            await asyncio.sleep(2)
        
        raise EnrollmentError(f"Lock not found after {timeout}s")
    
    async def connect(self) -> bool:
        """Connect to lock."""
        print(f"[*] Connecting to {self.lock_mac}...")
        
        if self.device is None:
            raise EnrollmentError("No connectable Bluetooth device selected")
        self.client = BleakClient(self.device, timeout=30.0)
        try:
            await self.client.connect()
            if not self.client.is_connected:
                raise EnrollmentError("Bluetooth connection did not remain open")
            print(f"[✓] Connected")
            return True
        except Exception as e:
            await self.disconnect()
            raise EnrollmentError("Bluetooth connection could not be established") from e
    
    async def trigger_enrollment(self) -> bool:
        """Trigger the enrollment handshake by sending initialization command."""
        if not self.client or not self.client.is_connected:
            raise EnrollmentError("Not connected")
        
        # Find security characteristic
        sec_char = None
        for service in self.client.services:
            for char in service.characteristics:
                if "write" in char.properties and "indicate" in char.properties:
                    # Prefer the one we know works (0000001e or 000000a6)
                    uuid_str = str(char.uuid)
                    if "001e" in uuid_str or "00a6" in uuid_str:
                        sec_char = char
                        break
            if sec_char:
                break
        
        if not sec_char:
            raise EnrollmentError("Security characteristic not found")
        
        print(f"[*] Triggering enrollment on {sec_char.uuid}")
        
        # Generate random nonces to send to lock
        rand1 = int.from_bytes(os.urandom(4), 'little')
        rand2 = int.from_bytes(os.urandom(4), 'little')
        
        # Build HandshakeBegin command (plaintext for factory-reset)
        # Format: [rand1: 4 LE][rand2: 4 LE][slot: 1][padding: 7]
        cmd = struct.pack("<II", rand1, rand2) + bytes([self.slot]) + b'\x00' * 7
        
        print(f"  Sending initialization command ({len(cmd)} bytes)...")
        
        # Set up notification handler
        responses = {"data": []}
        
        def on_notify(sender, data):
            responses["data"].append(data)
        
        try:
            await self.client.start_notify(sec_char, on_notify)
            print(f"[*] Subscribed to notifications")
            
            # Send the command
            await self.client.write_gatt_char(sec_char, cmd, response=False)
            print(f"[✓] Sent initialization command")
            
            # Wait for lock's nonce response
            print(f"[*] Waiting for lock to respond with nonces (10s)...")
            await asyncio.sleep(10)
            
            if responses["data"]:
                print(f"[✓] Received {len(responses['data'])} response(s)")
                # Use the first response that's long enough
                for resp in responses["data"]:
                    if len(resp) >= 8:
                        self.nonces = (resp[0:8], resp[8:16] if len(resp) >= 16 else b'\x00' * 8)
                        print(f"[✓] Extracted nonces")
                        return True
            
            raise EnrollmentError("No enrollment response received; no key was written")
        
        except Exception as e:
            raise EnrollmentError(f"Enrollment trigger failed: {e}")
    
    def derive_session_key(self) -> bytes:
        """Derive session key from captured nonces."""
        if not self.nonces or len(self.nonces[0]) < 8 or len(self.nonces[1]) < 8:
            raise EnrollmentError("Invalid nonces")
        
        lock_nonce, mobile_nonce = self.nonces
        self.session_key = mobile_nonce + lock_nonce
        
        return self.session_key
    
    def generate_offline_key(self) -> bytes:
        """Generate a random 16-byte offline key."""
        self.offline_key = os.urandom(16)
        return self.offline_key
    
    async def write_offline_key(self) -> bool:
        """Write the generated offline key to the lock using session key."""
        if not self.client or not self.client.is_connected:
            raise EnrollmentError("Not connected")
        
        if not self.session_key or not self.offline_key:
            raise EnrollmentError("Session key or offline key not ready")
        
        print(f"\n[*] Writing offline key to slot {self.slot}...")
        
        # Find security characteristic
        sec_char = None
        for service in self.client.services:
            for char in service.characteristics:
                if "write" in char.properties:
                    uuid_str = str(char.uuid)
                    if "0050" in uuid_str or "0037" in uuid_str:
                        sec_char = char
                        break
            if sec_char:
                break
        
        if not sec_char:
            raise EnrollmentError("Cannot find write characteristic for key")
        
        # Craft three frames: write lower, write upper, commit
        frames = [
            self._craft_key_frame(self.offline_key[0:8], 0x11),  # Write lower
            self._craft_key_frame(self.offline_key[8:16], 0x13),  # Write upper
            self._craft_commit_frame(),  # Commit
        ]
        
        for i, frame in enumerate(frames, 1):
            print(f"[*] Sending frame {i}/3 ({len(frame)} bytes)...")
            try:
                await self.client.write_gatt_char(sec_char, frame, response=False)
                await asyncio.sleep(0.5)
            except Exception as e:
                raise EnrollmentError(f"Frame {i} failed: {e}")
        
        print(f"[✓] Key write complete")
        return True
    
    def _craft_key_frame(self, key_data: bytes, opcode: int) -> bytes:
        """Craft an AES-encrypted key write frame."""
        if len(key_data) != 8:
            raise ValueError("key_data must be 8 bytes")
        
        # Compute checksum
        words = struct.unpack("<II", key_data)
        checksum = (-(sum(words))) & 0xFFFFFFFF
        
        # Build plaintext
        plaintext = struct.pack("<B", opcode) + key_data + struct.pack("<I", checksum) + b'\x00' * 3
        
        # Encrypt
        cipher = Cipher(algorithms.AES(self.session_key), modes.CBC(b'\x00' * 16))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        # Add frame trailer
        frame = ciphertext + bytes([0x0F, self.slot & 0xFF])
        return frame
    
    def _craft_commit_frame(self) -> bytes:
        """Craft the commit frame to finalize key write."""
        # Checksum of all 4 words in the key
        words = struct.unpack("<IIII", self.offline_key)
        checksum = (-(sum(words))) & 0xFFFFFFFF
        
        plaintext = struct.pack("<B", 0x15) + struct.pack("<I", checksum) + b'\x00' * 11
        
        cipher = Cipher(algorithms.AES(self.session_key), modes.CBC(b'\x00' * 16))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        frame = ciphertext + bytes([0x0F, self.slot & 0xFF])
        return frame
    
    async def disconnect(self):
        """Disconnect from lock."""
        if self.client is not None:
            try:
                await asyncio.wait_for(self.client.disconnect(), timeout=10.0)
                print(f"[✓] Disconnected")
            except Exception:
                pass
    
    async def enroll(self) -> bytes:
        """Complete enrollment flow and return the provisioned offline key."""
        try:
            await self.discover_lock()
            await self.connect()
            if not await self.trigger_enrollment():
                raise EnrollmentError("Enrollment handshake did not complete; no key was written")
            if not self.client.is_connected:
                raise EnrollmentError("Bluetooth disconnected during enrollment; no key was written")
            self.derive_session_key()
            self.generate_offline_key()
            await self.write_offline_key()
            
            print(f"\n[✓✓✓ ENROLLMENT COMPLETE ✓✓✓")
            print(f"[✓] Lock is now provisioned for offline control")
            
            return self.offline_key
        
        finally:
            await self.disconnect()
