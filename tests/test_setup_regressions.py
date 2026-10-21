"""Synthetic setup regressions; no Home Assistant runtime or hardware required."""

import ast
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest.mock import AsyncMock, patch
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "august_local"
spec = importlib.util.spec_from_file_location("august_enrollment_test", COMPONENT / "enrollment.py")
enrollment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enrollment)


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_failure_reports_stage_without_secret(self):
        characteristic = types.SimpleNamespace(properties=["write", "indicate"], uuid="0000001e-0000-1000-8000-0026bb765291")
        client = types.SimpleNamespace(
            is_connected=True,
            services=[types.SimpleNamespace(characteristics=[characteristic])],
            start_notify=AsyncMock(side_effect=RuntimeError("private payload")),
            write_gatt_char=AsyncMock(),
        )
        setup = enrollment.ASL05Enrollment("AA:BB:CC:DD:EE:FF", device=object())
        setup.client = client
        with self.assertRaises(enrollment.EnrollmentError) as caught:
            await setup.trigger_enrollment()
        self.assertEqual(caught.exception.stage, "notification_subscription")
        self.assertNotIn("private payload", str(caught.exception))
        client.write_gatt_char.assert_not_awaited()

    async def test_proxy_device_is_preserved_without_rescanning(self):
        device = object()
        client = types.SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(), is_connected=True)
        setup = enrollment.ASL05Enrollment("AA:BB:CC:DD:EE:FF", device=device)
        with patch.object(enrollment.BleakScanner, "discover", new_callable=AsyncMock) as scan:
            with patch.object(enrollment, "establish_connection", new_callable=AsyncMock, return_value=client) as factory:
                self.assertTrue(await setup.discover_lock())
                self.assertTrue(await setup.connect())
                factory.assert_awaited_once_with(enrollment.BleakClientWithServiceCache, device, "AA:BB:CC:DD:EE:FF", max_attempts=3, timeout=30.0)
                scan.assert_not_awaited()
                await setup.disconnect()
        client.disconnect.assert_awaited_once()

    async def test_connection_failure_cleans_up(self):
        client = types.SimpleNamespace(connect=AsyncMock(side_effect=TimeoutError()), disconnect=AsyncMock(), is_connected=False)
        setup = enrollment.ASL05Enrollment("AA:BB:CC:DD:EE:FF", device=object())
        setup.client = client
        with patch.object(enrollment, "establish_connection", new_callable=AsyncMock, side_effect=TimeoutError()):
            with self.assertRaisesRegex(enrollment.EnrollmentError, "could not be established"):
                await setup.connect()
        client.disconnect.assert_awaited_once()

    async def test_false_handshake_cannot_write_a_key(self):
        setup = enrollment.ASL05Enrollment("AA:BB:CC:DD:EE:FF", device=object())
        setup.discover_lock = AsyncMock(return_value=True)
        setup.connect = AsyncMock(return_value=True)
        setup.trigger_enrollment = AsyncMock(return_value=False)
        setup.write_offline_key = AsyncMock()
        setup.disconnect = AsyncMock()
        with self.assertRaises(enrollment.EnrollmentError):
            await setup.enroll()
        setup.write_offline_key.assert_not_awaited()
        setup.disconnect.assert_awaited_once()

    async def test_disconnected_handshake_cannot_write_a_key(self):
        setup = enrollment.ASL05Enrollment("AA:BB:CC:DD:EE:FF", device=object())
        setup.client = types.SimpleNamespace(is_connected=False)
        setup.discover_lock = AsyncMock(return_value=True)
        setup.connect = AsyncMock(return_value=True)
        setup.trigger_enrollment = AsyncMock(return_value=True)
        setup.write_offline_key = AsyncMock()
        setup.disconnect = AsyncMock()
        with self.assertRaisesRegex(enrollment.EnrollmentError, "disconnected during enrollment"):
            await setup.enroll()
        setup.write_offline_key.assert_not_awaited()
        setup.disconnect.assert_awaited_once()


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def make_flow(self, device):
        tree = ast.parse((COMPONENT / "config_flow.py").read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ConfigFlow")
        cls.bases = []
        cls.keywords = []
        cls.body = [node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("async_step_enroll", "_is_valid_mac")]
        lookup = Mock(return_value=device)
        factory = Mock()
        namespace = {
            "_LOGGER": Mock(),
            "bluetooth": types.SimpleNamespace(async_ble_device_from_address=lookup),
            "ASL05Enrollment": factory,
            "EnrollmentError": enrollment.EnrollmentError,
            "vol": types.SimpleNamespace(Schema=lambda value: value, Required=lambda value: value),
            "selector": types.SimpleNamespace(TextSelector=lambda value: value, TextSelectorConfig=lambda **kw: kw, TextSelectorType=types.SimpleNamespace(TEXT="text")),
        }
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "config_flow_methods", "exec"), namespace)
        flow = namespace["ConfigFlow"]()
        flow.hass = object()
        flow.async_show_form = lambda **kw: kw
        flow._finish_account_lock = AsyncMock()
        return flow, lookup, factory

    async def test_passive_advertisement_does_not_trigger_direct_connection(self):
        flow, lookup, factory = self.make_flow(None)
        result = await flow.async_step_enroll({"lock_mac": "aa:bb:cc:dd:ee:ff"})
        lookup.assert_called_once_with(flow.hass, "AA:BB:CC:DD:EE:FF", connectable=True)
        factory.assert_not_called()
        self.assertEqual(result["errors"], {"base": "no_connectable_device"})

    async def test_proxy_device_and_static_failure_error(self):
        device = object()
        flow, lookup, factory = self.make_flow(device)
        factory.return_value.enroll = AsyncMock(side_effect=enrollment.EnrollmentError("Not connected"))
        result = await flow.async_step_enroll({"lock_mac": "AA:BB:CC:DD:EE:FF"})
        factory.assert_called_once_with("AA:BB:CC:DD:EE:FF", device=device)
        self.assertEqual(result["errors"], {"base": "enrollment_failed"})
        flow._finish_account_lock.assert_not_awaited()


class MenuTests(unittest.TestCase):
    def test_every_menu_item_has_handler_and_shipped_translation(self):
        tree = ast.parse((COMPONENT / "config_flow.py").read_text())
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        inherited = {node.name for node in classes["AccountSteps"].body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for class_name, section in (("ConfigFlow", "config"), ("OptionsFlow", "options")):
            cls = classes[class_name]
            handlers = inherited | {node.name for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for call in ast.walk(cls):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or call.func.attr != "async_show_menu":
                    continue
                kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
                menu = kwargs["menu_options"]
                self.assertIsInstance(menu, dict)
                for option, label in menu.items():
                    self.assertTrue(label.strip())
                    self.assertIn("async_step_" + option, handlers)
                    for name in ("strings.json", "translations/en.json"):
                        data = json.loads((COMPONENT / name).read_text())
                        translated = data[section]["step"][kwargs["step_id"]]["menu_options"][option]
                        self.assertTrue(translated.strip(), (name, section, option))


if __name__ == "__main__":
    unittest.main()
