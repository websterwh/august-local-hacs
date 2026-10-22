"""Local ASL-05 PIN actions sharing the existing Yale Bluetooth connection."""

import asyncio
from contextlib import contextmanager
import logging
from pathlib import Path
import time

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util.yaml import load_yaml
from .protocol import ASL05Keypad, KeypadFailure

DOMAIN = "august_local"
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("entry_id"): cv.string,
                vol.Required("owned_slots"): [
                    vol.All(vol.Coerce(int), vol.Range(min=1, max=255))
                ],
                vol.Optional("pins_file", default="august_keypad_pins.yaml"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)
REFERENCE = vol.All(cv.string, vol.Match(r"^[A-Za-z_][A-Za-z0-9_]*$"))
SLOT = vol.All(vol.Coerce(int), vol.Range(min=1, max=255))


@contextmanager
def _private_protocol_logs():
    # Existing library logs can include decrypted frames even on errors.
    # Suppress its records for this transaction without muting other HA logs.
    class SuppressProtocol(logging.Filter):
        def filter(self, record):
            return not record.name.startswith(
                ("yalexs", "homeassistant.components.august")
            )

    guard = SuppressProtocol()
    handlers = set(logging.getLogger().handlers)
    for logger in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(logger, logging.Logger):
            handlers.update(logger.handlers)
    for handler in handlers:
        handler.addFilter(guard)
    try:
        yield
    finally:
        for handler in handlers:
            handler.removeFilter(guard)


def _read_pins(path):
    try:
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except Exception:
        raise HomeAssistantError(
            "Cannot read private PIN references file; contents withheld"
        ) from None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    if DOMAIN not in config:
        return True
    return await _setup(hass, config[DOMAIN])


async def async_setup_entry(hass, entry):
    result = await _setup(hass, entry.data, entry)
    from .panel import setup_panel

    await setup_panel(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor"])
    return result


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, ["binary_sensor"]):
        return False
    hass.data.get(DOMAIN, {}).pop("nearby_add", None)
    hass.data.get(DOMAIN, {}).pop("manager", None)
    for service in ("status", "program", "insert", "delete"):
        hass.services.async_remove(DOMAIN, service)
    return True


async def _setup(hass, settings, ui_entry=None):
    allowed = set(settings["owned_slots"])
    relative = Path(settings.get("pins_file", "august_keypad_pins.yaml"))
    if relative.is_absolute() or ".." in relative.parts:
        raise HomeAssistantError(
            "PIN references file must be inside the HA configuration folder"
        )
    pins_path = hass.config.path(str(relative))

    async def handle(call: ServiceCall):
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            if user is None or not user.is_active or not user.is_admin:
                raise HomeAssistantError(
                    "Administrator access required for direct keypad actions"
                )
        slot = call.data.get("slot")
        if slot is not None and slot not in (
            allowed | set(ui_entry.options.get("manager_slots", []))
            if ui_entry
            else allowed
        ):
            raise HomeAssistantError("Slot is not configured as owned; no command sent")
        entry = hass.config_entries.async_get_entry(settings["entry_id"])
        runtime = getattr(entry, "runtime_data", None) if entry else None
        push = getattr(runtime, "lock", None)
        if (
            entry is None
            or entry.domain != "yalexs_ble"
            or push is None
            or not getattr(push, "_running", False)
        ):
            raise HomeAssistantError(
                "Configured Yale Access Bluetooth entry is not loaded"
            )
        pin = previous = None
        if call.service != "status":
            refs = (
                dict(ui_entry.options.get("pins", {}))
                if ui_entry
                else await hass.async_add_executor_job(_read_pins, pins_path)
            )
            pin = refs.get(call.data["pin_reference"])
            previous = refs.get(
                call.data.get("previous_pin_reference", call.data["pin_reference"])
            )
            try:
                ASL05Keypad._validate(slot, pin)
                if call.service == "program":
                    ASL05Keypad._validate(slot, previous)
            except ValueError:
                raise HomeAssistantError(
                    "Missing or invalid private PIN reference; contents withheld"
                ) from None
        with _private_protocol_logs():
            try:
                await asyncio.wait_for(push._operation_lock.acquire(), 20)
            except TimeoutError:
                raise HomeAssistantError(
                    "Bluetooth connection is busy; no keypad command sent"
                ) from None
            stage = "connecting"
            try:
                try:
                    lock = await asyncio.wait_for(push._ensure_connected(), 45)
                    push._cancel_future_update()
                    stage = "reading status before keypad command"
                    await asyncio.wait_for(lock.lock_status(), 15)
                    stage = "sending keypad commands"
                    keypad = ASL05Keypad(lock)
                    if call.service == "program":
                        await keypad.program(slot, pin, replacing_pin=previous)
                    elif call.service == "insert":
                        from .inventory import slot_occupied

                        try:
                            occupied = await asyncio.wait_for(
                                slot_occupied(lock, slot), 10
                            )
                        except (
                            TimeoutError,
                            ValueError,
                            RuntimeError,
                            TypeError,
                            AttributeError,
                            BleakError,
                        ):
                            raise KeypadFailure(
                                "Slot occupancy could not be confirmed; no PIN insertion sent"
                            ) from None
                        if occupied:
                            raise KeypadFailure(
                                "Slot is occupied; no PIN insertion sent"
                            )
                        await keypad.insert(slot, pin)
                    elif call.service == "delete":
                        await keypad.delete(slot, current_pin=pin)
                    if call.service != "status":
                        stage = "checking status after confirmed keypad command"
                        await asyncio.wait_for(lock.lock_status(), 15)
                except KeypadFailure as exc:
                    raise HomeAssistantError(str(exc)) from None
                except Exception as exc:
                    raise HomeAssistantError(
                        f"Local keypad operation stopped while {stage}: {type(exc).__name__}; "
                        + (
                            "no keypad command sent"
                            if stage
                            in ("connecting", "reading status before keypad command")
                            else "keypad command confirmed, final status unavailable"
                            if stage == "checking status after confirmed keypad command"
                            else "write outcome may be unknown"
                        )
                    ) from None
                finally:
                    push._complete_operation(time.monotonic())
            finally:
                push._operation_lock.release()
        return {
            "confirmed": True,
            "operation": call.service,
            **(
                {"slot": slot} if slot is not None else {"owned_slots": sorted(allowed)}
            ),
        }

    common = {vol.Required("slot"): SLOT, vol.Required("pin_reference"): REFERENCE}
    hass.services.async_register(
        DOMAIN,
        "status",
        handle,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "program",
        handle,
        schema=vol.Schema(
            {**common, vol.Optional("previous_pin_reference"): REFERENCE}
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "insert",
        handle,
        schema=vol.Schema(common),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "delete",
        handle,
        schema=vol.Schema(common),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True
