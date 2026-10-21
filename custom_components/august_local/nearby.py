"""Passive per-proxy phone beacon proximity; not authentication."""
import re
import uuid

def beacon_identity(attributes):
    attrs = {str(k).lower(): v for k, v in attributes.items()}
    if all(k in attrs for k in ('uuid', 'major', 'minor')):
        identity = (str(uuid.UUID(str(attrs['uuid']))), int(attrs['major']), int(attrs['minor']))
    else:
        match = next((re.fullmatch(r'([0-9a-fA-F-]{36})[-_](\d+)[-_](\d+)', str(v))
                      for v in attrs.values() if re.fullmatch(r'([0-9a-fA-F-]{36})[-_](\d+)[-_](\d+)', str(v))), None)
        if match is None:
            raise ValueError('Enable the phone BLE Transmitter and Transmit toggle first')
        identity = (str(uuid.UUID(match[1])), int(match[2]), int(match[3]))
    if not all(0 <= n <= 65535 for n in identity[1:]):
        raise ValueError('Invalid phone beacon identifier')
    return identity

def matches_beacon(manufacturer_data, profile):
    data = manufacturer_data.get(0x004C, b'')
    return (len(data) >= 23 and data[:2] == b'\x02\x15'
            and data[2:18] == uuid.UUID(profile['uuid']).bytes
            and int.from_bytes(data[18:20], 'big') == profile['major']
            and int.from_bytes(data[20:22], 'big') == profile['minor'])

class NearGate:
    def __init__(self, threshold):
        self.threshold = threshold
        self.reset()
    def reset(self):
        self.start = None
        self.last = None
        self.samples = 0
        self.near = False
    def sample(self, timestamp, rssi, now):
        if now - timestamp > 3 or timestamp > now + 1 or (self.last is not None and timestamp <= self.last):
            return False
        if self.last is not None and timestamp - self.last > 3:
            self.reset()
        self.last = timestamp
        if rssi < self.threshold:
            self.start = None; self.samples = 0; self.near = False
        else:
            if self.start is None: self.start = timestamp
            self.samples += 1
            self.near = self.samples >= 3 and timestamp - self.start >= 2
        return True
