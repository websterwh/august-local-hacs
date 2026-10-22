"""Synthetic setup regressions; no Home Assistant runtime or hardware required."""

import ast
import asyncio
import contextlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from bleak.exc import BleakError


class _FakeAuthError(Exception):
    """Distinct AuthError stand-in — prevents transport exceptions from masking auth failures."""


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "august_local"

# Load enrollment module (no relative imports).
spec = importlib.util.spec_from_file_location(
    "august_enrollment_test", COMPONENT / "enrollment.py"
)
enrollment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enrollment)

# Load account.py with a stub package that supplies _private_protocol_logs.
# contextlib.nullcontext is a no-op context manager compatible with "with x():" usage.
_ACCT_PKG = "_august_local_acct_test"
_acct_pkg = types.ModuleType(_ACCT_PKG)
_acct_pkg._private_protocol_logs = contextlib.nullcontext
sys.modules[_ACCT_PKG] = _acct_pkg

_acct_spec = importlib.util.spec_from_file_location(
    _ACCT_PKG + ".account", COMPONENT / "account.py"
)
_acct_module = importlib.util.module_from_spec(_acct_spec)
_acct_module.__package__ = _ACCT_PKG
sys.modules[_ACCT_PKG + ".account"] = _acct_module
_acct_spec.loader.exec_module(_acct_module)


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_failure_reports_stage_without_secret(self):
        characteristic = types.SimpleNamespace(
            properties=["write", "indicate"],
            uuid="0000001e-0000-1000-8000-0026bb765291",
        )
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
        client = types.SimpleNamespace(
            connect=AsyncMock(), disconnect=AsyncMock(), is_connected=True
        )
        setup = enrollment.ASL05Enrollment("AA:BB:CC:DD:EE:FF", device=device)
        with patch.object(
            enrollment.BleakScanner, "discover", new_callable=AsyncMock
        ) as scan:
            with patch.object(
                enrollment,
                "establish_connection",
                new_callable=AsyncMock,
                return_value=client,
            ) as factory:
                self.assertTrue(await setup.discover_lock())
                self.assertTrue(await setup.connect())
                factory.assert_awaited_once_with(
                    enrollment.BleakClientWithServiceCache,
                    device,
                    "AA:BB:CC:DD:EE:FF",
                    max_attempts=3,
                    timeout=30.0,
                )
                scan.assert_not_awaited()
                await setup.disconnect()
        client.disconnect.assert_awaited_once()

    async def test_connection_failure_cleans_up(self):
        client = types.SimpleNamespace(
            connect=AsyncMock(side_effect=TimeoutError()),
            disconnect=AsyncMock(),
            is_connected=False,
        )
        setup = enrollment.ASL05Enrollment("AA:BB:CC:DD:EE:FF", device=object())
        setup.client = client
        with patch.object(
            enrollment,
            "establish_connection",
            new_callable=AsyncMock,
            side_effect=TimeoutError(),
        ):
            with self.assertRaisesRegex(
                enrollment.EnrollmentError, "could not be established"
            ):
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
        with self.assertRaisesRegex(
            enrollment.EnrollmentError, "disconnected during enrollment"
        ):
            await setup.enroll()
        setup.write_offline_key.assert_not_awaited()
        setup.disconnect.assert_awaited_once()


class FlowTests(unittest.IsolatedAsyncioTestCase):
    """Synthetic account wizard tests — no HA runtime or hardware required.

    AccountSteps, ConfigFlow, and OptionsFlow are loaded via AST rewrite
    (bases stripped) so no HA packages are needed at test time.
    """

    def _load_namespace(self):
        """Return a fresh namespace with all three flow classes, HA bases stripped."""
        tree = ast.parse((COMPONENT / "config_flow.py").read_text())
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        for cls in classes.values():
            # Keep AccountSteps as a base so inheritance works; strip only HA bases
            cls.bases = [
                b
                for b in cls.bases
                if isinstance(b, ast.Name) and b.id == "AccountSteps"
            ]
            cls.keywords = []

        # Placeholder updated after exec so isinstance(instance, ce.OptionsFlow) resolves
        ce = types.SimpleNamespace(ConfigFlow=object, OptionsFlow=object)

        vol_ns = types.SimpleNamespace(
            Schema=lambda d: d,
            Required=lambda k, **kw: k,
            UNDEFINED=None,
        )
        sel_ns = types.SimpleNamespace(
            SelectSelector=lambda c: c,
            SelectSelectorConfig=lambda **kw: kw,
            SelectOptionDict=lambda **kw: kw,
            TextSelector=lambda c: c,
            TextSelectorConfig=lambda **kw: kw,
            TextSelectorType=types.SimpleNamespace(PASSWORD="password"),
        )
        ns = {
            "_LOGGER": Mock(),
            "asyncio": asyncio,
            "logging": __import__("logging"),
            "vol": vol_ns,
            "selector": sel_ns,
            "bluetooth": types.SimpleNamespace(
                async_ble_device_from_address=Mock(return_value=None)
            ),
            "config_entries": ce,
            "ConnectedAugustAccount": Mock(side_effect=lambda rd: object()),
            "AccountError": Exception,
            "PushLock": Mock(),
            "BleakError": BleakError,
            "AuthError": _FakeAuthError,
            "_private_protocol_logs": Mock(return_value=MagicMock()),
            "DOMAIN": "august_local",
            "callback": lambda f: f,
        }
        exec(
            compile(
                ast.Module(
                    body=[
                        classes["AccountSteps"],
                        classes["ConfigFlow"],
                        classes["OptionsFlow"],
                    ],
                    type_ignores=[],
                ),
                "cf_synthetic",
                "exec",
            ),
            ns,
        )
        ce.OptionsFlow = ns["OptionsFlow"]
        ce.ConfigFlow = ns["ConfigFlow"]
        return ns

    def _config_flow(self, ns, *, august_entries=(), current_entries=()):
        flow = ns["ConfigFlow"]()
        flow.hass = types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=Mock(return_value=list(august_entries)),
                async_get_entry=Mock(return_value=None),
                flow=types.SimpleNamespace(
                    async_init=AsyncMock(
                        return_value={"type": "abort", "reason": "already_configured"}
                    ),
                    async_configure=AsyncMock(),
                ),
            )
        )
        flow._async_current_entries = Mock(return_value=list(current_entries))
        flow.async_abort = Mock(
            side_effect=lambda reason, **kw: {"type": "abort", "reason": reason}
        )
        flow.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
        flow.async_show_menu = Mock(side_effect=lambda **kw: {"type": "menu", **kw})
        flow.async_create_entry = Mock(
            side_effect=lambda **kw: {"type": "create_entry", **kw}
        )
        return flow

    def _options_flow(self, ns, *, ble_entry=None, august_entries=()):
        default_ble = types.SimpleNamespace(
            entry_id="ble_entry_1",
            domain="yalexs_ble",
            data={"address": "AA:BB:CC:DD:EE:FF"},
        )
        flow = ns["OptionsFlow"]()
        flow.config_entry = types.SimpleNamespace(
            data={"entry_id": "ble_entry_1"},
            options={},
        )
        flow.hass = types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_entries=Mock(return_value=list(august_entries)),
                async_get_entry=Mock(
                    return_value=ble_entry if ble_entry is not None else default_ble
                ),
                flow=types.SimpleNamespace(
                    async_init=AsyncMock(
                        return_value={"type": "abort", "reason": "already_configured"}
                    ),
                    async_configure=AsyncMock(),
                ),
            )
        )
        flow.async_abort = Mock(
            side_effect=lambda reason, **kw: {"type": "abort", "reason": reason}
        )
        flow.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
        flow.async_show_menu = Mock(side_effect=lambda **kw: {"type": "menu", **kw})
        flow.async_create_entry = Mock(
            side_effect=lambda **kw: {"type": "create_entry", **kw}
        )
        return flow

    # -- user step routing --

    async def test_user_aborts_when_already_configured(self):
        ns = self._load_namespace()
        flow = self._config_flow(ns, current_entries=[object()])
        result = await flow.async_step_user()
        flow.async_abort.assert_called_once_with(reason="single_instance_allowed")

    async def test_user_routes_directly_to_account_source(self):
        ns = self._load_namespace()
        flow = self._config_flow(ns)
        flow.async_step_account_source = AsyncMock(
            return_value={"type": "form", "step_id": "account_source"}
        )
        await flow.async_step_user()
        flow.async_step_account_source.assert_awaited_once()

    # -- account_source routing --

    async def test_account_source_no_august_entries_routes_to_setup_august(self):
        """When no loaded August entries exist, account_source delegates to setup_august."""
        ns = self._load_namespace()
        flow = self._config_flow(ns)  # no august_entries
        flow.async_step_setup_august = AsyncMock(
            return_value={"type": "form", "step_id": "setup_august"}
        )
        await flow.async_step_account_source()
        flow.async_step_setup_august.assert_awaited_once()

    async def test_account_source_shows_form_when_entries_present(self):
        ns = self._load_namespace()
        entry = types.SimpleNamespace(
            entry_id="aug1", title="August Home", runtime_data=object()
        )
        flow = self._config_flow(ns, august_entries=[entry])
        result = await flow.async_step_account_source()
        flow.async_show_form.assert_called_once()
        self.assertEqual(result["step_id"], "account_source")

    async def test_account_source_invalid_selection_shows_error(self):
        ns = self._load_namespace()
        entry = types.SimpleNamespace(
            entry_id="aug1", title="August Home", runtime_data=object()
        )
        flow = self._config_flow(ns, august_entries=[entry])
        result = await flow.async_step_account_source(
            {"cloud_entry_id": "no_such_entry"}
        )
        self.assertEqual(result.get("errors", {}).get("base"), "invalid_selection")
        flow.async_create_entry.assert_not_called()

    async def test_account_source_valid_entry_uses_connected_account_and_routes_to_lock(
        self,
    ):
        ns = self._load_namespace()
        rd = object()
        entry = types.SimpleNamespace(
            entry_id="aug1", title="August Home", runtime_data=rd
        )
        flow = self._config_flow(ns, august_entries=[entry])
        flow.async_step_account_lock = AsyncMock(
            return_value={"type": "form", "step_id": "account_lock"}
        )
        await flow.async_step_account_source({"cloud_entry_id": "aug1"})
        flow.async_step_account_lock.assert_awaited_once()
        ns["ConnectedAugustAccount"].assert_called_once_with(rd)

    # -- setup_august step --

    async def test_setup_august_shows_form_on_first_visit(self):
        """setup_august with no user_input shows the guidance form without aborting."""
        ns = self._load_namespace()
        flow = self._config_flow(ns)
        result = await flow.async_step_setup_august()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "setup_august")
        flow.async_abort.assert_not_called()

    async def test_setup_august_retry_still_no_entries_shows_error(self):
        """Submitting setup_august while still no loaded entries shows no_loaded_august_account."""
        ns = self._load_namespace()
        flow = self._config_flow(ns)  # no august_entries
        result = await flow.async_step_setup_august(user_input={})
        self.assertEqual(result["type"], "form")
        self.assertEqual(
            result.get("errors", {}).get("base"), "no_loaded_august_account"
        )
        flow.async_abort.assert_not_called()

    async def test_setup_august_picks_up_newly_loaded_entry(self):
        """When a loaded entry appears before submit, setup_august routes to account_source."""
        ns = self._load_namespace()
        entry = types.SimpleNamespace(
            entry_id="aug1", title="August Home", runtime_data=object()
        )
        flow = self._config_flow(ns, august_entries=[entry])
        flow.async_step_account_source = AsyncMock(
            return_value={"type": "form", "step_id": "account_source"}
        )
        await flow.async_step_setup_august(user_input={})
        flow.async_step_account_source.assert_awaited_once()

    # -- account_source entry filtering and selection guards --

    async def test_account_source_excludes_entries_without_runtime_data(self):
        """Entries missing runtime_data are excluded; submitting their ID is invalid."""
        ns = self._load_namespace()
        loaded = types.SimpleNamespace(
            entry_id="aug1", title="August", runtime_data=object()
        )
        unloaded = types.SimpleNamespace(
            entry_id="aug2", title="August2", runtime_data=None
        )
        flow = self._config_flow(ns, august_entries=[loaded, unloaded])
        # Initial form shows (only loaded entry passes the filter)
        result = await flow.async_step_account_source()
        self.assertEqual(result["step_id"], "account_source")
        # Submitting the unloaded entry ID is rejected as invalid_selection
        result2 = await flow.async_step_account_source({"cloud_entry_id": "aug2"})
        self.assertEqual(result2.get("errors", {}).get("base"), "invalid_selection")
        ns["ConnectedAugustAccount"].assert_not_called()

    async def test_account_source_multiple_entries_shows_selector_form(self):
        """Multiple loaded entries: form requires explicit selection, no entry created."""
        ns = self._load_namespace()
        entries = [
            types.SimpleNamespace(
                entry_id="aug1", title="August A", runtime_data=object()
            ),
            types.SimpleNamespace(
                entry_id="aug2", title="August B", runtime_data=object()
            ),
        ]
        flow = self._config_flow(ns, august_entries=entries)
        result = await flow.async_step_account_source()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "account_source")
        flow.async_create_entry.assert_not_called()
        ns["ConnectedAugustAccount"].assert_not_called()

    async def test_account_source_stale_id_routes_setup_august_when_all_entries_gone(
        self,
    ):
        """Stale entry ID submitted while all entries have since disappeared routes to setup_august."""
        ns = self._load_namespace()
        entry = types.SimpleNamespace(
            entry_id="aug1", title="August", runtime_data=object()
        )
        flow = self._config_flow(ns)
        # First call returns [entry] (form shown); re-check on invalid selection returns []
        flow.hass.config_entries.async_entries = Mock(side_effect=[[entry], []])
        flow.async_step_setup_august = AsyncMock(
            return_value={"type": "form", "step_id": "setup_august"}
        )
        await flow.async_step_account_source({"cloud_entry_id": "no_such_id"})
        flow.async_step_setup_august.assert_awaited_once()
        ns["ConnectedAugustAccount"].assert_not_called()

    async def test_account_source_wrapper_constructor_error_aborts_safely(self):
        """ConnectedAugustAccount constructor failure aborts with account_response_changed."""
        ns = self._load_namespace()
        entry = types.SimpleNamespace(
            entry_id="aug1", title="August", runtime_data=object()
        )
        flow = self._config_flow(ns, august_entries=[entry])
        ns["ConnectedAugustAccount"] = Mock(
            side_effect=RuntimeError("secret credentials xyz")
        )
        result = await flow.async_step_account_source({"cloud_entry_id": "aug1"})
        flow.async_abort.assert_called_once_with(reason="account_response_changed")
        # Raw exception text must not appear in the abort result
        self.assertNotIn("secret", str(result))
        self.assertNotIn("credentials", str(result))

    # -- options connect guard (fires before BLE lookup or discovery) --

    async def test_options_connect_aborts_wrong_domain_before_ble(self):
        """Linked entry with non-yalexs_ble domain aborts, forgets credentials, no BLE."""
        ns = self._load_namespace()
        wrong_ble = types.SimpleNamespace(
            entry_id="ble_entry_1", domain="zha", data={"address": "AA:BB:CC:DD:EE:FF"}
        )
        flow = self._options_flow(ns, ble_entry=wrong_ble)
        flow._forget_account = AsyncMock()
        flow._selected_lock = types.SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF", name="Front", serial="SN", keys=[(0, b"k")]
        )
        result = await flow.async_step_connect()
        flow._forget_account.assert_awaited_once()
        flow.async_abort.assert_called_once_with(reason="different_lock")
        ns["bluetooth"].async_ble_device_from_address.assert_not_called()

    async def test_options_connect_aborts_different_address_before_ble(self):
        """Linked entry with different address aborts, forgets credentials, no BLE."""
        ns = self._load_namespace()
        other_ble = types.SimpleNamespace(
            entry_id="ble_entry_1",
            domain="yalexs_ble",
            data={"address": "11:22:33:44:55:66"},
        )
        flow = self._options_flow(ns, ble_entry=other_ble)
        flow._forget_account = AsyncMock()
        flow._selected_lock = types.SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF", name="Front", serial="SN", keys=[(0, b"k")]
        )
        result = await flow.async_step_connect()
        flow._forget_account.assert_awaited_once()
        flow.async_abort.assert_called_once_with(reason="different_lock")
        ns["bluetooth"].async_ble_device_from_address.assert_not_called()

    async def test_options_connect_matching_address_consults_ble(self):
        """Matching address passes the guard and proceeds to the BLE device lookup."""
        ns = self._load_namespace()
        flow = self._options_flow(ns)  # default ble_entry has address AA:BB:CC:DD:EE:FF
        flow._selected_lock = types.SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF", name="Front", serial="SN", keys=[(0, b"k")]
        )
        result = await flow.async_step_connect(user_input={})
        ns["bluetooth"].async_ble_device_from_address.assert_called_once()
        self.assertEqual(
            result.get("errors", {}).get("base"), "bluetooth_connection_failed"
        )

    async def test_finish_account_lock_defense_aborts_non_yalexs_ble_domain(self):
        """_finish_account_lock defense-in-depth: current entry with wrong domain aborts."""
        ns = self._load_namespace()
        bad_linked = types.SimpleNamespace(
            entry_id="ble_entry_1",
            domain="august",
            data={"address": "AA:BB:CC:DD:EE:FF"},
        )
        flow = self._options_flow(ns, ble_entry=bad_linked)
        result = await flow._finish_account_lock(
            {
                "address": "AA:BB:CC:DD:EE:FF",
                "name": "Front",
                "serial": "SN",
                "key": "k",
                "slot": 1,
            }
        )
        flow.async_abort.assert_called_once_with(reason="different_lock")

    async def test_all_keys_rejected_never_creates_entry(self):
        """All keys raising AuthError must not produce a config entry."""
        ns = self._load_namespace()
        device = types.SimpleNamespace(address="AA:BB:CC:DD:EE:FF")
        ns["bluetooth"] = types.SimpleNamespace(
            async_ble_device_from_address=Mock(return_value=device)
        )
        pl_inst = Mock()
        pl_inst.validate = AsyncMock(side_effect=_FakeAuthError("auth rejected"))
        ns["PushLock"] = Mock(return_value=pl_inst)

        flow = self._options_flow(ns)
        flow._selected_lock = types.SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF",
            name="Front",
            serial="SN",
            keys=[(0, b"key0"), (1, b"key1")],
        )
        result = await flow.async_step_connect(user_input={})
        flow.async_create_entry.assert_not_called()
        self.assertEqual(result.get("errors", {}).get("base"), "bluetooth_auth_failed")

    async def test_transport_failure_does_not_retry_keys_or_create_entry(self):
        ns = self._load_namespace()
        ns[
            "bluetooth"
        ].async_ble_device_from_address.return_value = types.SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF"
        )
        lock = Mock()
        lock.validate = AsyncMock(side_effect=BleakError("private transport context"))
        ns["PushLock"].return_value = lock
        flow = self._options_flow(ns)
        flow._selected_lock = types.SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF",
            name="Test Door",
            serial="TEST",
            keys=[(1, "ab" * 16), (2, "cd" * 16)],
        )
        result = await flow.async_step_connect({})
        self.assertEqual(result["errors"]["base"], "bluetooth_connection_failed")
        ns["PushLock"].assert_called_once()
        flow.async_create_entry.assert_not_called()
        flow.hass.config_entries.flow.async_init.assert_not_awaited()

    async def test_first_key_rejected_second_valid_proceeds_to_discovery(self):
        """First key raises AuthError; second validates; discovery init called with winning slot/key."""
        ns = self._load_namespace()
        device = types.SimpleNamespace(address="AA:BB:CC:DD:EE:FF")
        ns["bluetooth"] = types.SimpleNamespace(
            async_ble_device_from_address=Mock(return_value=device)
        )
        pl_bad = Mock()
        pl_bad.validate = AsyncMock(side_effect=_FakeAuthError("slot 0 rejected"))
        pl_good = Mock()
        pl_good.validate = AsyncMock(return_value=None)
        ns["PushLock"] = Mock(side_effect=[pl_bad, pl_good])

        ble_entry = types.SimpleNamespace(
            entry_id="ble_1", data={"address": "AA:BB:CC:DD:EE:FF"}
        )
        flow = self._config_flow(ns)
        flow.hass.config_entries.flow.async_init = AsyncMock(
            return_value={"type": "create_entry", "result": ble_entry}
        )
        flow._selected_lock = types.SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF",
            name="Front Door",
            serial="SN001",
            keys=[(0, b"badkey"), (1, b"goodkey")],
        )
        await flow.async_step_connect(user_input={})
        flow.hass.config_entries.flow.async_init.assert_awaited_once()
        init_kwargs = flow.hass.config_entries.flow.async_init.call_args.kwargs
        self.assertEqual(init_kwargs["data"]["slot"], 1)
        self.assertEqual(init_kwargs["data"]["key"], b"goodkey")
        self.assertEqual(init_kwargs["data"]["address"], "AA:BB:CC:DD:EE:FF")
        flow.async_create_entry.assert_called_once()


class AccountTests(unittest.IsolatedAsyncioTestCase):
    """Behavioral tests for ConnectedAugustAccount — no HA imports, no network.

    Uses real yalexs/aiohttp packages (installed as project dependencies).
    _private_protocol_logs is stubbed with contextlib.nullcontext at module level.
    """

    def _make_runtime(self, token="tok-abc"):
        """Return (runtime, api_mock, gateway_mock) with empty lock list by default."""
        gateway = MagicMock()
        gateway.async_get_access_token = AsyncMock(return_value=token)
        api = MagicMock()
        api.async_get_operable_locks = AsyncMock(return_value=[])
        api.async_get_lock_detail = AsyncMock()
        return types.SimpleNamespace(_api=api, _gateway=gateway), api, gateway

    async def test_gateway_refreshed_on_each_locks_call(self):
        """async_get_access_token is called once per locks() invocation, never reused."""
        runtime, api, gateway = self._make_runtime()
        gateway.async_get_access_token.side_effect = ["first-token", "refreshed-token"]
        acct = _acct_module.ConnectedAugustAccount(runtime)
        await acct.locks()
        await acct.locks()
        self.assertEqual(gateway.async_get_access_token.await_count, 2)
        self.assertEqual(
            [call.args[0] for call in api.async_get_operable_locks.await_args_list],
            ["first-token", "refreshed-token"],
        )

    async def test_owner_lock_detail_uses_official_token_and_returns_installed_key(
        self,
    ):
        runtime, api, gateway = self._make_runtime(token="official-token")
        api.async_get_operable_locks.return_value = [
            types.SimpleNamespace(device_id="lock-id", device_name="Test Door")
        ]
        api.async_get_lock_detail.return_value = types.SimpleNamespace(
            mac_address="aa:bb:cc:dd:ee:ff",
            serial_number="TEST-SERIAL",
            loaded_offline_keys=[{"slot": 3, "key": "AB" * 16}],
        )
        acct = _acct_module.ConnectedAugustAccount(runtime)
        locks = await acct.locks()
        api.async_get_lock_detail.assert_awaited_once_with("official-token", "lock-id")
        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0].address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(locks[0].keys, [(3, "ab" * 16)])
        self.assertNotIn("token", vars(acct))

    async def test_token_passed_to_api_list_call(self):
        """Token returned by gateway is forwarded to async_get_operable_locks."""
        runtime, api, gateway = self._make_runtime(token="tok-xyz-123")
        acct = _acct_module.ConnectedAugustAccount(runtime)
        await acct.locks()
        api.async_get_operable_locks.assert_awaited_once()
        self.assertEqual(api.async_get_operable_locks.call_args.args[0], "tok-xyz-123")

    def test_close_leaves_official_api_session_untouched(self):
        """close() nulls borrowed refs but never calls close/revoke on api or gateway."""
        runtime, api, gateway = self._make_runtime()
        api.close = Mock()
        gateway.close = Mock()
        acct = _acct_module.ConnectedAugustAccount(runtime)
        acct.close()
        api.close.assert_not_called()
        gateway.close.assert_not_called()
        self.assertIsNone(acct.api)
        self.assertIsNone(acct.gateway)

    async def test_sanitized_error_does_not_leak_exception_message(self):
        """AccountError from locks() carries a fixed code string, not raw exception text."""
        from aiohttp import ClientError

        runtime, api, gateway = self._make_runtime()
        api.async_get_operable_locks = AsyncMock(
            side_effect=ClientError("SECRET TOKEN PAYLOAD XYZ")
        )
        acct = _acct_module.ConnectedAugustAccount(runtime)
        with self.assertLogs(_acct_module._LOGGER, level="WARNING") as logs:
            with self.assertRaises(_acct_module.AccountError) as ctx:
                await acct.locks()
        self.assertNotIn("SECRET TOKEN PAYLOAD XYZ", "\n".join(logs.output))
        err_text = str(ctx.exception)
        self.assertNotIn("SECRET", err_text)
        self.assertNotIn("TOKEN", err_text)
        self.assertNotIn("PAYLOAD", err_text)
        # The error code is a fixed, safe string
        self.assertTrue(ctx.exception.args[0].replace("_", "").isalpha())

    def test_incompatible_runtime_raises_account_error_not_attribute_error(self):
        """runtime without _api/_gateway raises AccountError, not a raw AttributeError."""
        with self.assertRaises(_acct_module.AccountError) as ctx:
            _acct_module.ConnectedAugustAccount(object())
        self.assertEqual(ctx.exception.args[0], "account_response_changed")


class MenuTests(unittest.TestCase):
    def test_every_menu_item_has_handler_and_shipped_translation(self):
        tree = ast.parse((COMPONENT / "config_flow.py").read_text())
        classes = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
        }
        inherited = {
            node.name
            for node in classes["AccountSteps"].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for class_name, section in (
            ("ConfigFlow", "config"),
            ("OptionsFlow", "options"),
        ):
            cls = classes[class_name]
            handlers = inherited | {
                node.name
                for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for call in ast.walk(cls):
                if (
                    not isinstance(call, ast.Call)
                    or not isinstance(call.func, ast.Attribute)
                    or call.func.attr != "async_show_menu"
                ):
                    continue
                kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
                menu = kwargs["menu_options"]
                self.assertIsInstance(menu, dict)
                for option, label in menu.items():
                    self.assertTrue(label.strip())
                    self.assertIn("async_step_" + option, handlers)
                    for name in ("strings.json", "translations/en.json"):
                        data = json.loads((COMPONENT / name).read_text())
                        translated = data[section]["step"][kwargs["step_id"]][
                            "menu_options"
                        ][option]
                        self.assertTrue(translated.strip(), (name, section, option))


if __name__ == "__main__":
    unittest.main()
