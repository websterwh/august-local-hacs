"""August ASL-05 legacy PIN commands; requires an authenticated yalexs-ble Lock.

PIN reads (Unity opcode 0x39) are unavailable on tested firmware 1.1.30.
Callers must own the slot and retain its PIN privately. Do not expose PINs to
Home Assistant entity states, service traces, recorder, or logs. Serialize
all access-control transactions on the shared lock connection.
"""
import asyncio
import re

class KeypadFailure(RuntimeError):
    """Nonsecret failure; a timeout can mean the write outcome is unknown."""

class ASL05Keypad:
    def __init__(self, lock):
        self.lock = lock
        self._transaction = asyncio.Lock()

    @staticmethod
    def _validate(slot, pin):
        if type(slot) is not int or not 1 <= slot <= 255:
            raise ValueError('Legacy slot must be an integer between 1 and 255')
        if not isinstance(pin, str) or not re.fullmatch(r'[0-9]{4,6}', pin):
            raise ValueError('August PIN must contain four to six ASCII digits')
        return bytes.fromhex(pin.ljust(14, 'f'))

    async def _send(self, opcode, pin=None, slot=None):
        session = self.lock.session
        if session is None:
            raise KeypadFailure('Not authenticated')
        cmd = session.build_command(opcode)
        if pin is not None:
            cmd[4:11] = pin
        if slot is not None:
            cmd[11] = slot
        if opcode == 0x2B:
            cmd[12] = 0x80
        def matches(frame):
            if len(frame) != 18 or frame[0] != 0xBB or frame[1] != opcode:
                return False
            # Successful commit echoes the actual slot, credential type, and PIN.
            # Accept failed results so their result code is surfaced promptly.
            return opcode != 0x2C or frame[15] != 0 or (
                frame[11] == slot and frame[12] == 0 and frame[4:11] == pin)
        try:
            response = await asyncio.wait_for(
                session.execute(cmd, f'asl05_keypad_{opcode:02x}', matches), 20)
        except Exception as exc:
            raise KeypadFailure(f'Opcode {opcode:02x}: {type(exc).__name__}; outcome unknown') from None
        if response[15] != 0:
            raise KeypadFailure(f'Opcode {opcode:02x}: result {response[15]}')

    async def program(self, slot, pin, *, replacing_pin):
        """Clear known owned slot, then set/schedule/commit; failures stop the chain.

        Clear uses the existing PIN, unlike yalexs-ble clear_keycode's blank PIN.
        A failure after clear can leave the owned slot empty. Never infer ownership
        or emptiness from get_keycode timeout.
        """
        encoded = self._validate(slot, pin)
        previous = self._validate(slot, replacing_pin)
        async with self._transaction:
            await self._send(0x28, previous, slot)
            await self._send(0x27, encoded)
            await self._send(0x2B)
            await self._send(0x2C, encoded, slot)

    async def insert(self, slot, pin):
        """Insert into a verified empty or acknowledged HA-cleared slot; no CLEAR.

        ASL-05 accepts commits to occupied slots too. The caller must reserve
        a known-unused range; this command is not an occupancy probe.
        """
        encoded = self._validate(slot, pin)
        async with self._transaction:
            await self._send(0x27, encoded)
            await self._send(0x2B)
            await self._send(0x2C, encoded, slot)

    async def delete(self, slot, *, current_pin):
        """Delete only a known owned slot using its current PIN."""
        encoded = self._validate(slot, current_pin)
        async with self._transaction:
            await self._send(0x28, encoded, slot)
