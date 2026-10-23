"""Synthetic HA adapters: no device, cloud, reset or motor calls."""

import ast
import asyncio
import logging
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/august_local"


class ManagerError(Exception):
    pass


class HomeAssistantError(Exception):
    pass


class KeypadFailure(Exception):
    pass


def extracted(path, name, namespace, parent=None, drop_imports=False):
    tree = ast.parse((ROOT / path).read_text())
    if parent:
        tree = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == parent
        )
    function = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name
    )
    for argument in function.args.args:
        argument.annotation = None
    if drop_imports:
        function.body = [n for n in function.body if not isinstance(n, ast.ImportFrom)]
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace[name]


class ClearAllAdapterTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self, model="ASL-05", authorized=True, admin=True):
        order = []
        manager = SimpleNamespace(
            consume_initialization=AsyncMock(return_value=authorized)
        )
        manager.consume_initialization.side_effect = lambda token: (
            order.append("authorize") or authorized
        )
        keypad = SimpleNamespace(clear_all=AsyncMock())
        keypad.clear_all.side_effect = lambda: order.append("clear")
        lock = SimpleNamespace(
            lock_status=AsyncMock(),
            lock_info=AsyncMock(return_value=SimpleNamespace(model=model)),
        )
        push = SimpleNamespace(
            _running=True,
            _operation_lock=asyncio.Lock(),
            _ensure_connected=AsyncMock(return_value=lock),
            _cancel_future_update=Mock(),
            _complete_operation=Mock(),
        )
        entry = SimpleNamespace(
            domain="yalexs_ble", runtime_data=SimpleNamespace(lock=push)
        )
        hass = SimpleNamespace(
            data={"august_local": {"manager": manager}},
            auth=SimpleNamespace(
                async_get_user=AsyncMock(
                    return_value=SimpleNamespace(is_active=True, is_admin=admin)
                )
            ),
            config_entries=SimpleNamespace(async_get_entry=Mock(return_value=entry)),
        )
        namespace = {
            "asyncio": asyncio,
            "time": time,
            "DOMAIN": "august_local",
            "hass": hass,
            "settings": {"entry_id": "target"},
            "allowed": {1},
            "ui_entry": SimpleNamespace(options={"manager_slots": [1]}),
            "HomeAssistantError": HomeAssistantError,
            "KeypadFailure": KeypadFailure,
            "ASL05Keypad": Mock(return_value=keypad),
            "_private_protocol_logs": nullcontext,
        }
        handle = extracted("__init__.py", "handle", namespace)
        call = SimpleNamespace(
            service="clear_all_keypad",
            data={"initialization_id": "a" * 32},
            context=SimpleNamespace(user_id="admin"),
        )
        return handle, call, manager, keypad, lock, push, order

    async def test_clear_requires_consumed_proof_and_sends_once_without_post_clear_poll(
        self,
    ):
        handle, call, manager, keypad, lock, push, order = self.adapter()
        result = await handle(call)
        self.assertTrue(result["confirmed"])
        self.assertEqual(order, ["authorize", "clear"])
        manager.consume_initialization.assert_awaited_once_with("a" * 32)
        keypad.clear_all.assert_awaited_once_with()
        lock.lock_status.assert_awaited_once_with()
        self.assertFalse(push._operation_lock.locked())
        push._complete_operation.assert_called_once()

    async def test_no_pending_confirmation_cannot_clear(self):
        handle, call, _, keypad, _, push, _ = self.adapter(authorized=False)
        with self.assertRaisesRegex(
            HomeAssistantError, "No pending administrator-confirmed"
        ):
            await handle(call)
        keypad.clear_all.assert_not_awaited()
        self.assertFalse(push._operation_lock.locked())

    async def test_other_model_blocked_before_authorization_or_clear(self):
        handle, call, manager, keypad, _, push, _ = self.adapter(model="OTHER")
        with self.assertRaisesRegex(HomeAssistantError, "restricted to ASL-05"):
            await handle(call)
        manager.consume_initialization.assert_not_awaited()
        keypad.clear_all.assert_not_awaited()
        self.assertFalse(push._operation_lock.locked())

    async def test_nonadministrator_blocked_before_bluetooth(self):
        handle, call, manager, keypad, _, push, _ = self.adapter(admin=False)
        with self.assertRaisesRegex(HomeAssistantError, "Administrator access"):
            await handle(call)
        manager.consume_initialization.assert_not_awaited()
        keypad.clear_all.assert_not_awaited()
        push._ensure_connected.assert_not_awaited()

    async def test_preflight_failure_does_not_consume_or_clear(self):
        handle, call, manager, keypad, lock, push, _ = self.adapter()
        lock.lock_status.side_effect = TimeoutError()
        with self.assertRaisesRegex(HomeAssistantError, "no keypad command sent"):
            await handle(call)
        manager.consume_initialization.assert_not_awaited()
        keypad.clear_all.assert_not_awaited()
        self.assertFalse(push._operation_lock.locked())

    async def test_native_failure_stops_without_retry(self):
        handle, call, _, keypad, _, push, _ = self.adapter()
        keypad.clear_all.side_effect = KeypadFailure("Opcode 29: result 2")
        with self.assertRaisesRegex(HomeAssistantError, "Opcode 29: result 2"):
            await handle(call)
        keypad.clear_all.assert_awaited_once()
        self.assertFalse(push._operation_lock.locked())


class Request(dict):
    def __init__(self, hass, payload, user):
        super().__init__(hass_user=user)
        self.app = {"hass": hass}
        self.payload = payload

    async def json(self):
        return self.payload


class DiscoveryControlTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        from bleak.exc import BleakError
        from yalexs_ble.session import DisconnectedError

        lock = SimpleNamespace(lock_status=AsyncMock())
        push = SimpleNamespace(
            _running=True,
            _operation_lock=asyncio.Lock(),
            _ensure_connected=AsyncMock(return_value=lock),
            _cancel_future_update=Mock(),
            _complete_operation=Mock(),
        )
        ble = SimpleNamespace(
            domain="yalexs_ble", runtime_data=SimpleNamespace(lock=push)
        )
        hass = SimpleNamespace(
            config_entries=SimpleNamespace(async_get_entry=Mock(return_value=ble))
        )
        read = AsyncMock(
            return_value={
                "slots": [{"slot": 26, "state": "unknown"}],
                "reason": "TIMEOUT",
                "diagnostic": {"slot": 26},
            }
        )
        discover = extracted(
            "panel.py",
            "discover",
            {
                "asyncio": asyncio,
                "time": time,
                "logging": logging,
                "__name__": "discovery_control_test",
                "hass": hass,
                "entry": SimpleNamespace(data={"entry_id": "target"}),
                "_private_protocol_logs": nullcontext,
                "discover_slots": read,
                "ManagerError": ManagerError,
                "BleakError": BleakError,
                "DisconnectedError": DisconnectedError,
            },
            drop_imports=True,
        )
        return discover, lock, push, read

    async def test_read_probe_has_successful_status_control_before_and_after_timeout(
        self,
    ):
        discover, lock, push, read = self.adapter()
        result = await discover(1, start_slot=26, maximum_slot=26)
        self.assertEqual(lock.lock_status.await_count, 2)
        read.assert_awaited_once_with(lock, 1, start_slot=26, maximum_slot=26)
        self.assertEqual(result["diagnostic"]["status_before"], "ok")
        self.assertEqual(result["diagnostic"]["status_after"], "ok")
        self.assertFalse(push._operation_lock.locked())
        push._complete_operation.assert_called_once()

    async def test_failed_preflight_sends_no_slot_read(self):
        discover, lock, push, read = self.adapter()
        lock.lock_status.side_effect = TimeoutError()
        with self.assertRaisesRegex(ManagerError, "No PIN write was sent"):
            await discover(1, start_slot=26, maximum_slot=26)
        read.assert_not_awaited()
        self.assertFalse(push._operation_lock.locked())
        push._complete_operation.assert_called_once()

    async def test_failed_postflight_preserves_original_occupancy_failure(self):
        discover, lock, push, _ = self.adapter()
        lock.lock_status.side_effect = [None, TimeoutError()]
        result = await discover(1, start_slot=26, maximum_slot=26)
        self.assertEqual(result["reason"], "TIMEOUT")
        self.assertEqual(result["diagnostic"]["status_after"], "TimeoutError")
        self.assertFalse(push._operation_lock.locked())


class PanelInitializationTests(unittest.IsolatedAsyncioTestCase):
    def api(self, admin=True):
        user = SimpleNamespace(is_active=True, is_admin=admin)

        def require_admin(value):
            if not value.is_admin:
                raise ManagerError("Administrator required")

        manager = SimpleNamespace(
            admin=Mock(side_effect=require_admin),
            initialize=AsyncMock(
                return_value={"initialized": True, "total": 2, "assigned": 2}
            ),
            create=AsyncMock(),
        )
        reader = AsyncMock(
            return_value={
                "slots": [{"slot": 26, "state": "unknown"}],
                "complete": False,
                "reason": "TIMEOUT slot=26",
            }
        )
        hass = SimpleNamespace(
            data={"august_local": {"manager": manager, "discover": reader}},
            auth=SimpleNamespace(async_get_users=AsyncMock(return_value=[user])),
        )
        view = SimpleNamespace(
            json=lambda result, status_code=200: {"status_code": status_code, **result}
        )
        post = extracted(
            "panel.py",
            "post",
            {
                "DOMAIN": "august_local",
                "ManagerError": ManagerError,
                "HomeAssistantError": HomeAssistantError,
            },
            parent="ManagerView",
        )
        return post, view, hass, manager, reader, user

    async def test_initialize_requires_exact_confirmation(self):
        post, view, hass, manager, _, user = self.api()
        result = await post(
            view,
            Request(hass, {"action": "initialize", "operation_id": "a" * 32}, user),
        )
        self.assertEqual(result["status_code"], 400)
        manager.initialize.assert_not_awaited()
        hass.auth.async_get_users.assert_not_awaited()

    async def test_initialize_forwards_only_explicit_confirmed_request(self):
        post, view, hass, manager, reader, user = self.api()
        result = await post(
            view,
            Request(
                hass,
                {
                    "action": "initialize",
                    "confirmation": "ERASE ALL KEYPAD CODES",
                    "operation_id": "a" * 32,
                    "count": 3,
                },
                user,
            ),
        )
        self.assertTrue(result["initialized"])
        manager.initialize.assert_awaited_once_with(
            user, [user], 3, operation_id="a" * 32
        )
        reader.assert_not_awaited()
        manager.create.assert_not_awaited()

    async def test_nonadmin_cannot_initialize_or_probe(self):
        for action in ("initialize", "probe"):
            post, view, hass, manager, reader, user = self.api(admin=False)
            result = await post(
                view,
                Request(
                    hass,
                    {
                        "action": action,
                        "slot": 26,
                        "confirmation": "ERASE ALL KEYPAD CODES",
                    },
                    user,
                ),
            )
            self.assertEqual(result["status_code"], 400)
            manager.initialize.assert_not_awaited()
            reader.assert_not_awaited()

    async def test_probe_returns_unknown_without_provisioning_or_writing(self):
        post, view, hass, manager, reader, user = self.api()
        result = await post(view, Request(hass, {"action": "probe", "slot": 26}, user))
        reader.assert_awaited_once_with(1, start_slot=26, maximum_slot=26)
        self.assertEqual(result["slots"], [{"slot": 26, "state": "unknown"}])
        manager.initialize.assert_not_awaited()
        manager.create.assert_not_awaited()

    async def test_probe_rejects_invalid_slot_before_bluetooth(self):
        for slot in (True, 0, 256, "26"):
            post, view, hass, _, reader, user = self.api()
            result = await post(
                view, Request(hass, {"action": "probe", "slot": slot}, user)
            )
            self.assertEqual(result["status_code"], 400)
            reader.assert_not_awaited()
