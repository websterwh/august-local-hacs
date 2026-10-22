"""Read-only keypad slot discovery; silence is never evidence of an empty slot."""

import asyncio

from bleak.exc import BleakError
from yalexs_ble.session import DisconnectedError


class InsertionBlocked(ValueError):
    """No PIN-changing command was sent."""


async def insert_owned_pin(lock, keypad, slot, pin, manager=None):
    """Use a confirmed HA clear, otherwise require a positive occupancy read."""
    cleared = manager is not None and await manager.consume_clearance(slot, pin)
    if not cleared:
        try:
            occupied = await asyncio.wait_for(slot_occupied(lock, slot), 10)
        except (
            BleakError,
            DisconnectedError,
            TimeoutError,
            ValueError,
            RuntimeError,
            TypeError,
            AttributeError,
        ):
            raise InsertionBlocked(
                "Slot occupancy could not be confirmed; no PIN insertion sent"
            ) from None
        if occupied:
            raise InsertionBlocked("Slot is occupied; no PIN insertion sent")
    await keypad.insert(slot, pin)


async def slot_occupied(lock, slot):
    """Read the echoed legacy slot and classify its BCD field privately."""
    session = lock.session
    if session is None:
        raise RuntimeError("Not authenticated")
    command = session.build_command(0x39)
    command[4:6] = slot.to_bytes(2, "little")

    def matches(frame):
        return (
            len(frame) == 18
            and frame[0] == 0xBB
            and frame[1] == 0x39
            and int.from_bytes(frame[4:6], "little") == slot
        )

    response = await session.execute(command, "keypad_slot_occupancy", matches)
    if not matches(response) or response[15] != 0:
        raise ValueError("Slot occupancy not confirmed")
    field = response[6:13].hex()
    digits = field.rstrip("f")
    if digits and (not digits.isascii() or not digits.isdigit()):
        raise ValueError("Malformed credential field")
    return bool(digits)


async def discover_slots(lock, limit, *, maximum_slot=255):
    """Find up to limit empty legacy slots using acknowledged KEYCODE_GET reads.

    Stop on the first unsupported, failed or malformed response. Never write to
    probe occupancy, and never return the decoded credential to the caller.
    """
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Choose between 1 and 50 slots")
    slots = []
    empty = 0
    for slot in range(1, maximum_slot + 1):
        try:
            occupied = await asyncio.wait_for(slot_occupied(lock, slot), 10)
        except (
            BleakError,
            DisconnectedError,
            TimeoutError,
            ValueError,
            RuntimeError,
            TypeError,
            AttributeError,
        ):
            slots.append({"slot": slot, "state": "unknown"})
            return {
                "slots": slots,
                "complete": False,
                "reason": "The lock did not confirm slot occupancy. No unknown slot can be allocated; a cloud code list alone cannot prove a local slot is empty.",
            }
        slots.append({"slot": slot, "state": "occupied" if occupied else "empty"})
        empty += not occupied
        if empty >= limit:
            return {"slots": slots, "complete": False, "reason": None}
    return {"slots": slots, "complete": True, "reason": None}
