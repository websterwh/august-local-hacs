"""Read-only occupancy response tests; no hardware or Home Assistant imports."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

SPEC = importlib.util.spec_from_file_location(
    "august_inventory_test",
    Path(__file__).resolve().parents[1] / "custom_components/august_local/inventory.py",
)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class InventoryTests(unittest.IsolatedAsyncioTestCase):
    def lock(self, slot=2, field=b"\xff" * 7, result=0):
        response = bytearray(18)
        response[0:2] = b"\xbb\x39"
        response[4:6] = slot.to_bytes(2, "little")
        response[6:13] = field
        response[15] = result
        session = SimpleNamespace(
            build_command=lambda opcode: bytearray(18),
            execute=AsyncMock(return_value=response),
        )
        return SimpleNamespace(session=session)

    async def test_empty_requires_successful_slot_echo_and_empty_credential(self):
        lock = self.lock()
        self.assertFalse(await inventory.slot_occupied(lock, 2))
        command, _, matcher = lock.session.execute.await_args.args
        self.assertEqual(command[4:6], b"\x02\x00")
        self.assertTrue(matcher(lock.session.execute.return_value))
        self.assertFalse(matcher(bytearray(18)))

    async def test_occupied_not_returned_as_empty_or_exposed(self):
        lock = self.lock(field=bytes.fromhex("1234ffffffffff"))
        self.assertIs(await inventory.slot_occupied(lock, 2), True)

    async def test_wrong_slot_rejected_even_if_session_returns_it(self):
        with self.assertRaises(ValueError):
            await inventory.slot_occupied(self.lock(slot=3), 2)

    async def test_nonzero_result_is_not_empty(self):
        with self.assertRaises(ValueError):
            await inventory.slot_occupied(self.lock(result=1), 2)

    async def test_malformed_bcd_is_not_empty(self):
        with self.assertRaises(ValueError):
            await inventory.slot_occupied(
                self.lock(field=bytes.fromhex("abffffffffffff")), 2
            )

    async def test_timeout_stops_scan_without_allocating_unknown(self):
        with patch.object(
            inventory, "slot_occupied", AsyncMock(side_effect=TimeoutError())
        ) as read:
            result = await inventory.discover_slots(object(), 2)
        self.assertEqual(result["slots"], [{"slot": 1, "state": "unknown"}])
        self.assertFalse(result["complete"])
        read.assert_awaited_once()

    async def test_upstream_disconnect_is_unknown_not_empty_or_internal_error(self):
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(side_effect=inventory.DisconnectedError()),
        ) as read:
            result = await inventory.discover_slots(object(), 2)
        self.assertEqual(result["slots"], [{"slot": 1, "state": "unknown"}])
        self.assertFalse(result["complete"])
        read.assert_awaited_once()

    async def test_limit_counts_only_positive_empty_reads(self):
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(side_effect=[True, False, True, False]),
        ):
            result = await inventory.discover_slots(object(), 2)
        self.assertEqual(
            [r["slot"] for r in result["slots"] if r["state"] == "empty"], [2, 4]
        )
        self.assertIsNone(result["reason"])

    async def test_scan_does_not_assume_capacity_beyond_acknowledged_range(self):
        with patch.object(inventory, "slot_occupied", AsyncMock(return_value=True)):
            result = await inventory.discover_slots(object(), 1, maximum_slot=2)
        self.assertTrue(result["complete"])
        self.assertTrue(all(r["state"] == "occupied" for r in result["slots"]))


if __name__ == "__main__":
    unittest.main()
