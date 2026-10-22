"""Pure manager policy tests; no lock writes or HA runtime."""

import copy
import ast
import asyncio
from contextlib import nullcontext
import time
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import re
from unittest.mock import AsyncMock, Mock, patch
from bleak.exc import BleakError
from yalexs_ble.session import DisconnectedError

spec = importlib.util.spec_from_file_location(
    "pin_manager_test",
    Path(__file__).resolve().parents[1] / "custom_components/august_local/manager.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def person(uid, admin=False, active=True, system=False):
    return SimpleNamespace(
        id=uid, name=uid, is_admin=admin, is_active=active, system_generated=system
    )


def empty(slot, owner=None):
    return {
        "slot": slot,
        "name": "Available",
        "owner_id": owner,
        "source": "local_discovered",
        "status": "reserved",
        "access_type": "always",
        "verified_empty": True,
    }


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    def manager(self, records=None, slots=None):
        state = {"records": copy.deepcopy(records or {})}
        save = AsyncMock()
        operate = AsyncMock()
        discover = AsyncMock(
            return_value={
                "slots": slots
                if slots is not None
                else [
                    {"slot": 1, "state": "occupied"},
                    {"slot": 2, "state": "empty"},
                    {"slot": 3, "state": "empty"},
                    {"slot": 4, "state": "empty"},
                ],
                "complete": False,
                "reason": None,
            }
        )
        return (
            module.PinManager(state, save, operate, discover=discover),
            save,
            operate,
            discover,
        )

    async def test_two_users_get_two_verified_slots_idempotently(self):
        m, save, operate, discover = self.manager()
        admin = person("admin", True)
        other = person("other")
        result = await m.provision(
            admin,
            [
                admin,
                other,
                person("disabled", active=False),
                person("system", system=True),
            ],
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual(
            {r["owner_id"] for r in m.state["records"].values()}, {"admin", "other"}
        )
        self.assertNotIn("1", m.state["records"])
        again = await m.provision(admin, [admin, other])
        self.assertEqual(again["allocated"], 0)
        discover.assert_awaited_once()
        operate.assert_not_awaited()

    async def test_count_is_total_and_extra_pin_uses_unassigned_capacity(self):
        m, _, operate, _ = self.manager()
        admin = person("admin", True)
        await m.provision(admin, [admin], count=3)
        self.assertEqual(len(m.state["records"]), 3)
        slot = await m.create(admin, "123456", "Guest")
        self.assertEqual(slot, 2)
        operate.assert_awaited_once_with("insert", 2, "123456", "123456")
        self.assertEqual(m.state["records"]["2"]["status"], "programmed_unverified")
        self.assertNotIn("verified_empty", m.state["records"]["2"])
        result = await m.provision(admin, [admin], count=3)
        self.assertEqual(result["allocated"], 0)

    async def test_unknown_inventory_allocates_nothing(self):
        m, _, operate, _ = self.manager(
            slots=[{"slot": 1, "state": "occupied"}, {"slot": 2, "state": "unknown"}]
        )
        with self.assertRaises(module.ManagerError):
            await m.provision(person("admin", True), [person("one")])
        self.assertEqual(m.state["records"], {})
        operate.assert_not_awaited()

    async def test_capacity_growth_skips_already_reserved_empty_slots(self):
        m, _, operate, _ = self.manager({"2": empty(2)})
        result = await m.provision(person("admin", True), [], count=3)
        self.assertEqual(result["total"], 3)
        self.assertEqual(set(m.state["records"]), {"2", "3", "4"})
        operate.assert_not_awaited()

    async def test_legacy_metadata_not_trusted_and_existing_pin_preserved(self):
        records = {
            "1": {
                "slot": 1,
                "source": "local",
                "status": "active",
                "pin": "1234",
                "owner_id": "admin",
            },
            "2": {"slot": 2, "source": "local_reserved", "status": "reserved"},
        }
        m, _, operate, _ = self.manager(records)
        self.assertNotIn("2", m.state["records"])
        self.assertEqual(m.state["records"]["1"]["pin"], "1234")
        self.assertEqual(m.state["records"]["1"]["status"], "programmed_unverified")
        with self.assertRaises(module.ManagerError):
            await m.create(person("admin", True), "5678")
        operate.assert_not_awaited()

    async def test_cannot_take_another_users_empty_slot(self):
        m, _, operate, _ = self.manager({"2": empty(2, "someone_else")})
        with self.assertRaises(module.ManagerError):
            await m.create(person("admin", True), "1234")
        operate.assert_not_awaited()

    async def test_timeout_retains_pending_and_never_restores_empty(self):
        m, _, operate, _ = self.manager({"2": empty(2)})
        operate.side_effect = TimeoutError()
        with self.assertRaises(module.ManagerError):
            await m.create(person("admin", True), "1234")
        r = m.state["records"]["2"]
        self.assertEqual(r["status"], "needs_attention")
        self.assertEqual(r["pending_pin"], "1234")
        self.assertNotIn("verified_empty", r)
        with self.assertRaises(module.ManagerError):
            await m.mutate(person("admin", True), 2, "program", "5678")
        self.assertEqual(operate.await_count, 1)

    async def test_preflight_block_does_not_claim_write_recovery(self):
        m, _, operate, _ = self.manager({"2": empty(2)})
        operate.side_effect = module.InsertNotStarted()
        with self.assertRaisesRegex(module.ManagerError, "before any new PIN was sent"):
            await m.create(person("admin", True), "1234")
        record = m.state["records"]["2"]
        self.assertEqual(record["status"], "reserved")
        self.assertNotIn("pending_pin", record)
        self.assertNotIn("pin", record)
        self.assertNotIn("verified_empty", record)
        with self.assertRaises(module.ManagerError):
            await m.create(person("admin", True), "5678")
        self.assertEqual(operate.await_count, 1)

    async def test_existing_uncertain_pin_is_never_discarded_on_reload(self):
        m, _, operate, _ = self.manager(
            {
                "1": {
                    "slot": 1,
                    "source": "local",
                    "status": "needs_attention",
                    "pending_pin": "1234",
                }
            }
        )
        self.assertEqual(m.state["records"]["1"]["pending_pin"], "1234")
        self.assertEqual(m.state["records"]["1"]["status"], "needs_attention")
        operate.assert_not_awaited()

    async def test_restricted_import_never_becomes_always(self):
        m, _, operate, _ = self.manager(
            {
                "2": {
                    "slot": 2,
                    "source": "august_import",
                    "status": "imported",
                    "access_type": "recurring",
                    "pin": "1234",
                }
            }
        )
        original = copy.deepcopy(m.state)
        with self.assertRaises(module.ManagerError):
            await m.mutate(person("admin", True), 2, "program", "5678")
        self.assertEqual(m.state, original)
        operate.assert_not_awaited()

    async def test_non_admin_cannot_provision(self):
        m, _, operate, discover = self.manager()
        with self.assertRaises(module.ManagerError):
            await m.provision(person("user"), [person("user")])
        discover.assert_not_awaited()
        operate.assert_not_awaited()

    async def test_duplicate_scan_entries_do_not_prove_empty(self):
        m, _, operate, _ = self.manager(
            slots=[{"slot": 1, "state": "empty"}, {"slot": 1, "state": "occupied"}]
        )
        with self.assertRaises(module.ManagerError):
            await m.provision(person("admin", True), [person("user")])
        operate.assert_not_awaited()

    async def test_duplicate_pin_is_rejected_without_another_write(self):
        m, _, operate, _ = self.manager({"2": empty(2), "3": empty(3)})
        admin = person("admin", True)
        await m.create(admin, "1234")
        with self.assertRaises(module.ManagerError):
            await m.create(admin, "1234")
        self.assertEqual(operate.await_count, 1)

    async def test_import_does_not_disclose_cloud_pin_to_reserved_user(self):
        m, _, operate, _ = self.manager({"2": empty(2, "personal-user")})
        result = await m.import_codes(
            person("admin", True), [{"slot": 2, "pin": "1234"}]
        )
        self.assertEqual(result, {"added": 0, "skipped": 1})
        self.assertNotIn("pin", m.state["records"]["2"])
        operate.assert_not_awaited()

    async def test_definite_rejection_requires_new_discovery(self):
        m, _, operate, discover = self.manager({"2": empty(2, "admin")})
        admin = person("admin", True)
        operate.side_effect = module.InsertRejected()
        with self.assertRaises(module.ManagerError):
            await m.create(admin, "1234")
        self.assertNotIn("verified_empty", m.state["records"]["2"])
        self.assertNotIn("pending_pin", m.state["records"]["2"])
        result = await m.provision(admin, [admin])
        self.assertEqual(result["assigned"], 1)
        self.assertTrue(m.state["records"]["2"]["verified_empty"])
        discover.assert_awaited_once()

    async def test_failure_does_not_publish_partial_capacity(self):
        m, _, operate, _ = self.manager(slots=[{"slot": 2, "state": "empty"}])
        with self.assertRaises(module.ManagerError):
            await m.provision(person("admin", True), [person("one"), person("two")])
        self.assertEqual(m.state["records"], {})
        operate.assert_not_awaited()

    async def test_delete_then_readd_known_slot_does_not_use_occupancy_read(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "custom_components/august_local/inventory.py"
        )
        inventory_spec = importlib.util.spec_from_file_location(
            "known_clear_inventory", path
        )
        inventory = importlib.util.module_from_spec(inventory_spec)
        inventory_spec.loader.exec_module(inventory)
        m, save, operate, _ = self.manager(
            {
                "2": {
                    "slot": 2,
                    "source": "local",
                    "status": "programmed_unverified",
                    "pin": "1234",
                    "owner_id": "admin",
                }
            }
        )
        keypad = SimpleNamespace(insert=AsyncMock())

        async def insert(slot, pin):
            self.assertNotIn("cleared_before_insert", m.state["records"][str(slot)])
            self.assertNotIn(
                "cleared_before_insert", save.await_args.args[0]["records"][str(slot)]
            )

        keypad.insert.side_effect = insert

        async def operation(action, slot, pin, previous):
            if action == "insert":
                await inventory.insert_owned_pin(object(), keypad, slot, pin, m)

        operate.side_effect = operation
        admin = person("admin", True)
        await m.mutate(admin, 2, "delete")
        self.assertEqual(m.state["records"]["2"]["status"], "cleared")
        with patch.object(
            inventory, "slot_occupied", AsyncMock(side_effect=TimeoutError())
        ) as probe:
            slot = await m.create(admin, "5678")
            probe.assert_not_awaited()
        self.assertEqual(slot, 2)
        keypad.insert.assert_awaited_once_with(2, "5678")
        self.assertEqual(m.state["records"]["2"]["pin"], "5678")
        self.assertFalse(await m.consume_clearance(2, "5678"))

    async def test_recovery_clears_only_retained_candidates_then_inserts_same_slot(
        self,
    ):
        m, _, operate, discover = self.manager(
            {
                "2": {
                    "slot": 2,
                    "source": "local",
                    "status": "needs_attention",
                    "pin": "1234",
                    "pending_pin": "5678",
                    "owner_id": "user",
                    "name": "My code",
                }
            }
        )
        await m.recover(person("user"), 2, "9012")
        self.assertEqual(
            [call.args for call in operate.await_args_list],
            [
                ("delete", 2, "1234", "1234"),
                ("delete", 2, "5678", "5678"),
                ("insert", 2, "9012", "9012"),
            ],
        )
        record = m.state["records"]["2"]
        self.assertEqual(record["pin"], "9012")
        self.assertEqual(record["owner_id"], "user")
        self.assertEqual(record["name"], "My code")
        self.assertNotIn("pending_pin", record)
        self.assertNotIn("cleared_before_insert", record)
        discover.assert_not_awaited()

    async def test_recovery_stops_at_first_unconfirmed_clear(self):
        m, _, operate, _ = self.manager(
            {
                "2": {
                    "slot": 2,
                    "source": "local",
                    "status": "needs_attention",
                    "pending_pin": "5678",
                    "owner_id": "admin",
                }
            }
        )
        operate.side_effect = TimeoutError()
        with self.assertRaises(module.ManagerError):
            await m.recover(person("admin", True), 2, "9012")
        operate.assert_awaited_once_with("delete", 2, "5678", "5678")
        self.assertEqual(m.state["records"]["2"]["pending_pin"], "5678")
        self.assertEqual(m.state["records"]["2"]["status"], "needs_attention")
        self.assertNotIn("cleared_before_insert", m.state["records"]["2"])

    async def test_recovery_cannot_clear_unknown_imported_or_other_users_slot(self):
        for source, owner in [("august_import", "user"), ("local", "someone_else")]:
            m, _, operate, _ = self.manager(
                {
                    "2": {
                        "slot": 2,
                        "source": source,
                        "status": "needs_attention",
                        "pending_pin": "5678",
                        "owner_id": owner,
                    }
                }
            )
            with self.assertRaises(module.ManagerError):
                await m.recover(person("user"), 2, "9012")
            operate.assert_not_awaited()

    async def test_restart_discards_stale_clearance_without_discarding_candidate(self):
        m, _, _, _ = self.manager(
            {
                "2": {
                    "slot": 2,
                    "source": "local",
                    "status": "pending",
                    "pending_pin": "5678",
                    "cleared_before_insert": True,
                }
            }
        )
        self.assertFalse(await m.consume_clearance(2, "5678"))
        self.assertEqual(m.state["records"]["2"]["pending_pin"], "5678")

    async def test_clearance_requires_matching_slot_candidate_and_source(self):
        m, save, _, _ = self.manager()
        m.state["records"]["2"] = {
            "slot": 2,
            "source": "local",
            "status": "pending",
            "pending_pin": "5678",
            "cleared_before_insert": True,
        }
        self.assertFalse(await m.consume_clearance(2, "1234"))
        self.assertFalse(await m.consume_clearance(3, "5678"))
        m.state["records"]["2"]["source"] = "local_discovered"
        self.assertFalse(await m.consume_clearance(2, "5678"))
        save.assert_not_awaited()

    async def test_change_known_pin_keeps_original_program_transaction(self):
        m, _, operate, discover = self.manager(
            {
                "2": {
                    "slot": 2,
                    "source": "local",
                    "status": "programmed_unverified",
                    "pin": "1234",
                    "owner_id": "user",
                }
            }
        )
        await m.mutate(person("user"), 2, "program", "5678")
        operate.assert_awaited_once_with("program", 2, "5678", "1234")
        discover.assert_not_awaited()

    async def test_old_blocked_record_requires_admin_and_last_known_pin(self):
        record = {
            "slot": 2,
            "source": "local_discovered",
            "status": "reserved",
            "owner_id": "user",
        }
        m, _, operate, _ = self.manager({"2": record})
        with self.assertRaises(module.ManagerError):
            await m.recover(person("user"), 2, "5678", "1234")
        with self.assertRaises(module.ManagerError):
            await m.recover(person("admin", True), 2, "5678")
        operate.assert_not_awaited()
        self.assertEqual(m.state["records"]["2"], record)
        await m.recover(person("admin", True), 2, "5678", "1234")
        self.assertEqual(
            [call.args for call in operate.await_args_list],
            [("delete", 2, "1234", "1234"), ("insert", 2, "5678", "5678")],
        )
        self.assertEqual(m.state["records"]["2"]["owner_id"], "user")

    async def test_restore_does_not_clear_code_known_to_another_slot(self):
        m, _, operate, _ = self.manager(
            {
                "2": {"slot": 2, "source": "local_discovered", "status": "reserved"},
                "3": {
                    "slot": 3,
                    "source": "local",
                    "status": "programmed_unverified",
                    "pin": "1234",
                },
            }
        )
        with self.assertRaises(module.ManagerError):
            await m.recover(person("admin", True), 2, "5678", "1234")
        operate.assert_not_awaited()

    async def test_verified_reservation_cannot_be_restored_using_supplied_old_code(
        self,
    ):
        m, _, operate, _ = self.manager({"2": empty(2)})
        with self.assertRaises(module.ManagerError):
            await m.recover(person("admin", True), 2, "5678", "1234")
        operate.assert_not_awaited()


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    """Execute the real nested adapter with fake HA services, not hardware."""

    def adapter(self, error):
        tree = ast.parse(
            (
                Path(__file__).resolve().parents[1]
                / "custom_components/august_local/panel.py"
            ).read_text()
        )
        setup = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "setup_panel"
        )
        operate = next(
            node
            for node in setup.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "operate"
        )
        entry = SimpleNamespace(options={})
        hass = SimpleNamespace(
            services=SimpleNamespace(
                async_call=AsyncMock(side_effect=RuntimeError(error))
            ),
            config_entries=SimpleNamespace(async_update_entry=Mock()),
        )
        namespace = {
            "entry": entry,
            "hass": hass,
            "state": {"records": {"2": {"slot": 2}}},
            "DOMAIN": "august_local",
            "re": re,
            "InsertRejected": module.InsertRejected,
            "InsertNotStarted": module.InsertNotStarted,
        }
        exec(
            compile(
                ast.Module(body=[operate], type_ignores=[]),
                "panel_adapter_test",
                "exec",
            ),
            namespace,
        )
        return namespace["operate"], hass

    async def test_only_proven_no_write_messages_are_classified_as_blocked(self):
        for message in (
            "Slot occupancy could not be confirmed; no PIN insertion sent",
            "Slot is occupied; no PIN insertion sent",
        ):
            with self.subTest(message=message):
                operate, hass = self.adapter(message)
                with self.assertRaises(module.InsertNotStarted):
                    await operate("insert", 2, "1234", "1234")
                hass.services.async_call.assert_awaited_once()
                final_options = hass.config_entries.async_update_entry.call_args.kwargs[
                    "options"
                ]
                self.assertNotIn("_manager_new", final_options["pins"])
                self.assertNotIn("_manager_previous", final_options["pins"])

    async def test_unknown_write_error_is_not_classified_as_not_started(self):
        operate, _ = self.adapter("Opcode 2c: TimeoutError; outcome unknown")
        with self.assertRaises(RuntimeError):
            await operate("insert", 2, "1234", "1234")

    async def test_discovery_connect_disconnect_releases_lock_and_sends_no_write(self):
        tree = ast.parse(
            (
                Path(__file__).resolve().parents[1]
                / "custom_components/august_local/panel.py"
            ).read_text()
        )
        setup = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "setup_panel"
        )
        discover = next(
            node
            for node in setup.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "discover"
        )
        discover.body = [
            node for node in discover.body if not isinstance(node, ast.ImportFrom)
        ]
        push = SimpleNamespace(
            _running=True,
            _operation_lock=asyncio.Lock(),
            _ensure_connected=AsyncMock(side_effect=DisconnectedError()),
            _cancel_future_update=Mock(),
            _complete_operation=Mock(),
        )
        ble = SimpleNamespace(
            domain="yalexs_ble", runtime_data=SimpleNamespace(lock=push)
        )
        read = AsyncMock()
        namespace = {
            "entry": SimpleNamespace(data={"entry_id": "test"}),
            "hass": SimpleNamespace(
                config_entries=SimpleNamespace(async_get_entry=Mock(return_value=ble))
            ),
            "asyncio": asyncio,
            "time": time,
            "_private_protocol_logs": nullcontext,
            "discover_slots": read,
            "ManagerError": module.ManagerError,
            "DisconnectedError": DisconnectedError,
            "BleakError": BleakError,
        }
        exec(
            compile(
                ast.Module(body=[discover], type_ignores=[]), "discovery_test", "exec"
            ),
            namespace,
        )
        with self.assertRaisesRegex(module.ManagerError, "No PIN write was sent"):
            await namespace["discover"](2)
        self.assertFalse(push._operation_lock.locked())
        read.assert_not_awaited()
        push._cancel_future_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
