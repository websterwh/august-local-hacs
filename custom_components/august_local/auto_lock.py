"""Read/write onboard auto-lock timers over an existing authenticated session."""

import asyncio
import time
from homeassistant.exceptions import HomeAssistantError
from . import DOMAIN, _private_protocol_logs


async def setting(session, opcode, value=None):
    cmd = session.build_command(opcode)
    cmd[4] = 0x28
    if value is not None:
        cmd[8:12] = value.to_bytes(4, "little")

    def matches(frame):
        return (
            len(frame) == 18
            and frame[0] == 0xBB
            and frame[1] == opcode
            and frame[4] == 0x28
        )

    response = await asyncio.wait_for(
        session.execute(cmd, "local_auto_lock_setting", matches), 20
    )
    return int.from_bytes(response[8:12], "little")


def decode(value):
    first, second = value & 0xFFFF, value >> 16
    return {
        "mode": "timer" if second else "instant" if first else "off",
        "seconds": first or second,
        "never_opened_seconds": first,
        "door_closed_seconds": second,
    }


def encode(mode, seconds):
    if mode == "off":
        return 0
    if (
        mode not in ("timer", "instant")
        or type(seconds) is not int
        or not 1 <= seconds <= 65534
    ):
        raise ValueError("Choose a mode and an integer delay from 1 to 65534 seconds")
    return seconds | (seconds << 16) if mode == "timer" else seconds


async def operate(hass, data):
    entry = hass.data[DOMAIN]["entry"]
    ble = hass.config_entries.async_get_entry(entry.data["entry_id"])
    push = getattr(getattr(ble, "runtime_data", None), "lock", None)
    if push is None or not getattr(push, "_running", False):
        raise HomeAssistantError("Yale Bluetooth integration is not ready")
    writing = data.get("action") == "auto_lock_save"
    value = encode(data.get("mode"), data.get("seconds")) if writing else None
    acquired = False
    with _private_protocol_logs():
        try:
            await asyncio.wait_for(push._operation_lock.acquire(), 20)
            acquired = True
            lock = await asyncio.wait_for(push._ensure_connected(), 45)
            push._cancel_future_update()
            if writing:
                await setting(lock.session, 0x03, value)
            actual = await setting(lock.session, 0x04)
            if writing and actual != value:
                raise HomeAssistantError(
                    "The lock retained a different timer. Read the setting before retrying."
                )
            return {"ok": True, "confirmed": True, **decode(actual)}
        except HomeAssistantError:
            raise
        except Exception:
            if not writing:
                raise HomeAssistantError(
                    "Bluetooth disconnected or timed out while reading auto-lock. No setting was changed; check the proxy connection and use Read again."
                ) from None
            raise HomeAssistantError(
                "Auto-lock could not be confirmed over Bluetooth. Read the setting before retrying; a save may have reached the lock."
            ) from None
        finally:
            if acquired:
                push._complete_operation(time.monotonic())
                push._operation_lock.release()
