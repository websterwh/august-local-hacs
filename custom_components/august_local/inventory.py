"""Read-only keypad slot discovery; silence is never evidence of an empty slot."""

import asyncio
import logging

from bleak.exc import BleakError
from yalexs_ble.session import DisconnectedError

_LOGGER = logging.getLogger(__name__)
READ_TIMEOUT = 12.0
READ_FAILSAFE = 13.0


class InsertionBlocked(ValueError):
    """No PIN-changing command was sent."""


class SlotReadError(ValueError):
    """Slot read failed; carries safe diagnostic only, no raw frames or credentials."""

    CODE_FRAME_SHORT = "FRAME_SHORT"
    CODE_ECHO_MISMATCH = "ECHO_MISMATCH"
    CODE_RESULT_NONZERO = "RESULT_NONZERO"
    CODE_MALFORMED = "MALFORMED"
    CODE_TIMEOUT = "TIMEOUT"
    CODE_DISCONNECTED = "DISCONNECTED"
    CODE_COMM_ERROR = "COMM_ERROR"

    def __init__(
        self,
        code,
        *,
        result=None,
        frame_length=None,
        echo_match=None,
        ack_seen=None,
        response_opcodes=(),
        notifications_seen=None,
    ):
        self.code = code
        self.result = result
        self.frame_length = frame_length
        self.echo_match = echo_match
        self.ack_seen = ack_seen
        self.response_opcodes = response_opcodes
        self.notifications_seen = notifications_seen
        super().__init__(code)


async def insert_owned_pin(lock, keypad, slot, pin, manager=None):
    """Use a confirmed HA clear, otherwise require a positive occupancy read."""
    cleared = manager is not None and await manager.consume_clearance(slot, pin)
    if not cleared:
        try:
            occupied = await asyncio.wait_for(slot_occupied(lock, slot), READ_FAILSAFE)
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

    # ack_seen is set inside the closure when an AA39 acknowledgement arrives
    # ahead of the BB39 data frame.  The flag is read in the TimeoutError handler
    # so it survives even when the data frame never arrives.
    ack_seen = False
    response_opcodes = []
    last_notification = getattr(session, "_last_callback_time", None)

    def matches(frame):
        """Accept only BB39 data frames; note AA39 ACK in closure, keep waiting."""
        nonlocal ack_seen
        if len(frame) == 18 and frame[0] in (0xAA, 0xBB):
            opcode = int(frame[1])
            if opcode not in response_opcodes and len(response_opcodes) < 8:
                response_opcodes.append(opcode)
        if len(frame) == 18 and frame[0] == 0xAA and frame[1] == 0x39:
            ack_seen = True
            return False  # ACK observed but not the data response; keep waiting
        return len(frame) == 18 and frame[0] == 0xBB and frame[1] == 0x39

    try:
        # Allow the upstream 10-second response window plus its cooldown/write.
        # Keep an inner deadline so safe observations survive the outer failsafe.
        response = await asyncio.wait_for(
            session.execute(command, "keypad_slot_occupancy", matches),
            READ_TIMEOUT,
        )
    except TimeoutError:
        current_notification = getattr(session, "_last_callback_time", None)
        raise SlotReadError(
            SlotReadError.CODE_TIMEOUT,
            ack_seen=ack_seen,
            response_opcodes=tuple(response_opcodes),
            notifications_seen=(
                current_notification != last_notification
                if current_notification is not None and last_notification is not None
                else None
            ),
        ) from None
    except DisconnectedError:
        raise SlotReadError(SlotReadError.CODE_DISCONNECTED) from None
    except BleakError:
        raise SlotReadError(SlotReadError.CODE_COMM_ERROR) from None
    # CancelledError is intentionally not caught; it propagates to signal that the
    # outer wait_for budget expired and the caller must not swallow it.

    frame_len = len(response)

    # Defence-in-depth: even though the matcher already required BB39 + len 18,
    # validate the returned frame before touching any field offsets.
    if frame_len != 18 or response[0] != 0xBB or response[1] != 0x39:
        raise SlotReadError(SlotReadError.CODE_FRAME_SHORT, frame_length=frame_len)

    # Read both the result byte and the slot echo before any occupancy decision so
    # that RESULT_NONZERO carries the correct echo_match even when the echo is also
    # wrong.  Result is checked first because a nonzero result is more specific than
    # a mismatched echo and should be the primary rejection code.
    raw_result = response[15]
    echo_slot = int.from_bytes(response[4:6], "little")
    echo_ok = echo_slot == slot

    if raw_result != 0:
        raise SlotReadError(
            SlotReadError.CODE_RESULT_NONZERO,
            result=raw_result,
            frame_length=frame_len,
            echo_match=echo_ok,
        )

    if not echo_ok:
        raise SlotReadError(
            SlotReadError.CODE_ECHO_MISMATCH,
            result=raw_result,
            frame_length=frame_len,
            echo_match=False,
        )

    # Validate BCD credential field: bytes 6–12 (7 bytes = 14 nibbles).
    # Valid nibbles are decimal digits 0–9 and the padding sentinel 0xF.
    field_hex = response[6:13].hex()
    digits = field_hex.rstrip("f")

    # Empty: strictly all-FF; any non-FF nibble must be a valid 4–6 digit PIN.
    if not digits:
        return False

    # Occupied: 4–6 decimal ASCII digits after removing trailing F padding.
    # Lengths 1–3 and ≥7 are malformed; non-digit nibbles (0xA–0xE) are also
    # malformed.
    if not digits.isdigit() or not (4 <= len(digits) <= 6):
        raise SlotReadError(
            SlotReadError.CODE_MALFORMED,
            frame_length=frame_len,
            echo_match=True,
        )

    return True


def _build_reason(code, slot, result=None, frame_length=None):
    """Assemble a diagnostic reason from fixed codes and numeric values only."""
    labels = {
        SlotReadError.CODE_TIMEOUT: "occupancy read timed out",
        SlotReadError.CODE_DISCONNECTED: "occupancy read disconnected",
        SlotReadError.CODE_COMM_ERROR: "occupancy read had a Bluetooth communication failure",
        SlotReadError.CODE_RESULT_NONZERO: "occupancy read was rejected",
        SlotReadError.CODE_ECHO_MISMATCH: "response did not echo the requested slot",
        SlotReadError.CODE_FRAME_SHORT: "response had an invalid frame shape",
        SlotReadError.CODE_MALFORMED: "response did not contain valid occupancy data",
    }
    parts = [code, f"slot={slot}"]
    if result is not None:
        parts.append(f"result={result}")
    if frame_length is not None:
        parts.append(f"length={frame_length}")
    return (
        f"Slot {slot} {labels.get(code, 'occupancy read failed')} ({' '.join(parts)})."
    )


async def discover_slots(lock, limit, *, start_slot=1, maximum_slot=255):
    """Find up to limit empty legacy slots using acknowledged KEYCODE_GET reads.

    Stop on the first unsupported, failed or malformed response. Never write to
    probe occupancy, and never return the decoded credential to the caller.
    """
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Choose between 1 and 50 slots")
    if (
        type(start_slot) is not int
        or type(maximum_slot) is not int
        or not 1 <= start_slot <= maximum_slot <= 255
    ):
        raise ValueError("Choose a slot range within 1 through 255")
    slots = []
    empty = 0
    for slot in range(start_slot, maximum_slot + 1):
        try:
            occupied = await asyncio.wait_for(slot_occupied(lock, slot), READ_FAILSAFE)
        except (
            SlotReadError,
            TimeoutError,
            BleakError,
            DisconnectedError,
            RuntimeError,
            TypeError,
            AttributeError,
            ValueError,
        ) as exc:
            # Classify the exception using fixed codes; never embed str(exc).
            if isinstance(exc, SlotReadError):
                code = exc.code
                exc_class = "SlotReadError"
                result_val = exc.result
                frame_len_val = exc.frame_length
                echo_match_val = exc.echo_match
                ack_seen_val = exc.ack_seen
                response_opcodes = list(exc.response_opcodes)
                notifications_seen = exc.notifications_seen
            elif isinstance(exc, TimeoutError):
                # Outer wait_for fired; slot_occupied's inner timeout did not.
                code = SlotReadError.CODE_TIMEOUT
                exc_class = "TimeoutError"
                result_val = frame_len_val = echo_match_val = None
                ack_seen_val = None
                response_opcodes = []
                notifications_seen = None
            else:
                # Unexpected exception not wrapped by slot_occupied (e.g. direct
                # mock in tests or an unanticipated BLE layer error).
                code = type(exc).__name__
                exc_class = type(exc).__name__
                result_val = frame_len_val = echo_match_val = None
                ack_seen_val = None
                response_opcodes = []
                notifications_seen = None

            _LOGGER.warning(
                "Slot read diagnostic: slot=%d code=%s result=%s length=%s ack_seen=%s notifications_seen=%s response_opcodes=%s",
                slot,
                code,
                result_val,
                frame_len_val,
                ack_seen_val,
                notifications_seen,
                response_opcodes,
            )
            reason = _build_reason(code, slot, result_val, frame_len_val)
            diagnostic = {
                "slot": slot,
                "stage": "slot_read",
                "code": code,
                "exception_class": exc_class,
                "reason": reason,
                "result": result_val,
                "frame_length": frame_len_val,
                "echo_match": echo_match_val,
                "ack_seen": ack_seen_val,
                "notifications_seen": notifications_seen,
                "response_opcodes": response_opcodes,
            }
            slots.append({"slot": slot, "state": "unknown"})
            return {
                "slots": slots,
                "complete": False,
                "reason": reason,
                "diagnostic": diagnostic,
            }
        slots.append({"slot": slot, "state": "occupied" if occupied else "empty"})
        empty += not occupied
        if empty >= limit:
            return {"slots": slots, "complete": False, "reason": None}
    return {"slots": slots, "complete": True, "reason": None}
