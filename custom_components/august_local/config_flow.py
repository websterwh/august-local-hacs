"""UI setup, including one-time import of an installed August owner key."""

import asyncio
import logging

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.core import callback
from homeassistant.helpers import selector
from yalexs_ble import AuthError, PushLock

from . import DOMAIN, _private_protocol_logs
from .account import AccountError, ConnectedAugustAccount

_LOGGER = logging.getLogger(__name__)


class AccountSteps:
    _account = None
    _account_locks = None
    _selected_lock = None

    async def _forget_account(self):
        if self._account:
            self._account.close()
        self._account = None
        self._account_locks = None
        self._selected_lock = None

    async def async_step_account_source(self, user_input=None):
        entries = [
            e
            for e in self.hass.config_entries.async_entries("august")
            if getattr(e, "runtime_data", None) is not None
        ]
        if not entries:
            return await self.async_step_setup_august()
        errors = {}
        if user_input is not None:
            chosen = user_input["cloud_entry_id"]
            entry = next((e for e in entries if e.entry_id == chosen), None)
            if entry is None:
                # Re-check: entry may have disappeared while the form was visible.
                entries = [
                    e
                    for e in self.hass.config_entries.async_entries("august")
                    if getattr(e, "runtime_data", None) is not None
                ]
                if not entries:
                    return await self.async_step_setup_august()
                errors["base"] = "invalid_selection"
            else:
                await self._forget_account()
                try:
                    self._account = ConnectedAugustAccount(entry.runtime_data)
                except AccountError:
                    return self.async_abort(reason="account_response_changed")
                return await self.async_step_account_lock()
        choices = [
            selector.SelectOptionDict(value=e.entry_id, label=e.title) for e in entries
        ]
        return self.async_show_form(
            step_id="account_source",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "cloud_entry_id",
                        default=entries[0].entry_id
                        if len(entries) == 1
                        else vol.UNDEFINED,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=choices)
                    )
                }
            ),
        )

    async def async_step_setup_august(self, user_input=None):
        """Shown when no loaded official August entry exists yet."""
        errors = {}
        if user_input is not None:
            entries = [
                e
                for e in self.hass.config_entries.async_entries("august")
                if getattr(e, "runtime_data", None) is not None
            ]
            if not entries:
                errors["base"] = "no_loaded_august_account"
            else:
                return await self.async_step_account_source()
        return self.async_show_form(
            step_id="setup_august",
            errors=errors,
            data_schema=vol.Schema({}),
        )

    async def async_step_account_lock(self, user_input=None):
        errors = {}
        if self._account is None:
            return await self.async_step_account_source()
        if self._account_locks is None:
            try:
                self._account_locks = await self._account.locks()
            except AccountError as exc:
                await self._forget_account()
                return self.async_abort(reason=str(exc))
        if not self._account_locks:
            await self._forget_account()
            return self.async_abort(reason="no_account_locks")
        if user_input is not None:
            lock = next(
                (x for x in self._account_locks if x.lock_id == user_input["lock_id"]),
                None,
            )
            if lock is None:
                errors["base"] = "invalid_selection"
            elif not lock.keys:
                errors["base"] = "no_offline_key"
            else:
                self._selected_lock = lock
                return await self.async_step_connect()
        choices = [
            selector.SelectOptionDict(value=x.lock_id, label=x.name)
            for x in self._account_locks
        ]
        return self.async_show_form(
            step_id="account_lock",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("lock_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=choices)
                    )
                }
            ),
        )

    async def async_step_connect(self, user_input=None):
        errors = {}
        lock = self._selected_lock
        if lock is None:
            return await self.async_step_account_source()
        if isinstance(self, config_entries.OptionsFlow):
            ble_entry = self.hass.config_entries.async_get_entry(
                self.config_entry.data["entry_id"]
            )
            if (
                ble_entry is None
                or ble_entry.domain != "yalexs_ble"
                or ble_entry.data.get("address", "").upper() != lock.address.upper()
            ):
                await self._forget_account()
                return self.async_abort(reason="different_lock")
        if user_input is not None:
            device = bluetooth.async_ble_device_from_address(
                self.hass, lock.address, True
            )
            if device is None:
                errors["base"] = "bluetooth_connection_failed"
            else:
                found = None
                try:
                    with _private_protocol_logs():
                        for slot, key in lock.keys:
                            try:
                                await asyncio.wait_for(
                                    PushLock(
                                        lock.serial, device.address, device, key, slot
                                    ).validate(),
                                    45,
                                )
                                found = (slot, key)
                                break
                            except AuthError:
                                continue
                except (
                    BleakError,
                    TimeoutError,
                    OSError,
                    ValueError,
                    TypeError,
                    RuntimeError,
                    KeyError,
                    AttributeError,
                ) as exc:
                    _LOGGER.warning(
                        "August Bluetooth key validation failed: exception=%s",
                        type(exc).__name__,
                    )
                    errors["base"] = "bluetooth_connection_failed"
                if found is None and not errors:
                    errors["base"] = "bluetooth_auth_failed"
                if found:
                    data = {
                        "name": lock.name,
                        "address": lock.address,
                        "serial": lock.serial,
                        "key": found[1],
                        "slot": found[0],
                    }
                    try:
                        return await self._finish_account_lock(data)
                    finally:
                        await self._forget_account()
        return self.async_show_form(
            step_id="connect",
            errors=errors,
            data_schema=vol.Schema({}),
            description_placeholders={"name": lock.name},
        )

    async def _finish_account_lock(self, data):
        if isinstance(self, config_entries.OptionsFlow):
            current = self.hass.config_entries.async_get_entry(
                self.config_entry.data["entry_id"]
            )
            if (
                current is None
                or current.domain != "yalexs_ble"
                or current.data.get("address", "").upper() != data["address"].upper()
            ):
                return self.async_abort(reason="different_lock")
        result = await self.hass.config_entries.flow.async_init(
            "yalexs_ble", context={"source": "integration_discovery"}, data=data
        )
        if result["type"] == "form":
            if result.get("step_id") != "integration_discovery_confirm":
                return self.async_abort(reason="bluetooth_setup_failed")
            result = await self.hass.config_entries.flow.async_configure(
                result["flow_id"], {}
            )
        if result["type"] == "create_entry":
            ble = result["result"]
        elif result["type"] == "abort" and result.get("reason") == "already_configured":
            ble = next(
                (
                    e
                    for e in self.hass.config_entries.async_entries("yalexs_ble")
                    if e.data.get("address", "").upper() == data["address"]
                ),
                None,
            )
            if ble is None:
                return self.async_abort(reason="bluetooth_setup_failed")
        else:
            return self.async_abort(reason="bluetooth_setup_failed")
        settings = {"entry_id": ble.entry_id, "owned_slots": [], "ui_pins": True}
        if isinstance(self, config_entries.OptionsFlow):
            if self.config_entry.data["entry_id"] != ble.entry_id:
                return self.async_abort(reason="different_lock")
            return self.async_create_entry(
                title="", data=dict(self.config_entry.options)
            )
        return self.async_create_entry(title="August Local", data=settings)


class ConfigFlow(AccountSteps, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return await self.async_step_account_source()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(AccountSteps, config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "manage": "Open PIN management",
                "account_source": "Reconnect account and Bluetooth key",
            },
        )

    async def async_step_manage(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="", data=dict(self.config_entry.options)
            )
        return self.async_show_form(step_id="manage", data_schema=vol.Schema({}))
