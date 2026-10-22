"""Auto-lock lifecycle tests without HA, Bluetooth or setting writes."""

import ast
import asyncio
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock

from yalexs_ble.session import DisconnectedError


class HomeAssistantError(Exception):
    pass


class AutoLockTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "custom_components/august_local/auto_lock.py"
        )
        tree = ast.parse(path.read_text())
        functions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        push = SimpleNamespace(
            _running=True,
            _operation_lock=asyncio.Lock(),
            _ensure_connected=AsyncMock(side_effect=DisconnectedError()),
            _cancel_future_update=Mock(),
            _complete_operation=Mock(),
        )
        entry = SimpleNamespace(data={"entry_id": "test"})
        hass = SimpleNamespace(
            data={"august_local": {"entry": entry}},
            config_entries=SimpleNamespace(
                async_get_entry=Mock(
                    return_value=SimpleNamespace(
                        runtime_data=SimpleNamespace(lock=push)
                    )
                )
            ),
        )
        namespace = {
            "asyncio": asyncio,
            "time": time,
            "HomeAssistantError": HomeAssistantError,
            "DOMAIN": "august_local",
            "_private_protocol_logs": nullcontext,
        }
        exec(
            compile(
                ast.Module(body=functions, type_ignores=[]), "auto_lock_test", "exec"
            ),
            namespace,
        )
        namespace["setting"] = AsyncMock()
        return namespace, hass, push

    async def test_disconnected_read_sends_no_setting_and_releases_lock(self):
        namespace, hass, push = self.adapter()
        with self.assertRaisesRegex(HomeAssistantError, "No setting was changed"):
            await namespace["operate"](hass, {"action": "auto_lock_read"})
        self.assertFalse(push._operation_lock.locked())
        namespace["setting"].assert_not_awaited()
        push._complete_operation.assert_called_once()

    async def test_uncertain_save_is_not_automatically_retried(self):
        namespace, hass, push = self.adapter()
        push._ensure_connected.side_effect = None
        push._ensure_connected.return_value = SimpleNamespace(session=object())
        namespace["setting"].side_effect = DisconnectedError()
        with self.assertRaisesRegex(
            HomeAssistantError, "a save may have reached the lock"
        ):
            await namespace["operate"](
                hass, {"action": "auto_lock_save", "mode": "timer", "seconds": 30}
            )
        namespace["setting"].assert_awaited_once()
        self.assertFalse(push._operation_lock.locked())


if __name__ == "__main__":
    unittest.main()
