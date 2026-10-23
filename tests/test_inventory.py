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

    # ------------------------------------------------------------------ #
    # Existing occupancy-classification tests                             #
    # ------------------------------------------------------------------ #

    async def test_empty_requires_successful_slot_echo_and_empty_credential(self):
        lock = self.lock()
        self.assertFalse(await inventory.slot_occupied(lock, 2))
        command, _, matcher = lock.session.execute.await_args.args
        self.assertEqual(command[4:6], b"\x02\x00")
        # Matcher accepts a valid BB39 frame.
        self.assertTrue(matcher(lock.session.execute.return_value))
        # Matcher rejects all-zero frames (wrong opcode).
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

    async def test_insertion_without_clear_proof_still_checks_occupancy(self):
        keypad = SimpleNamespace(insert=AsyncMock())
        manager = SimpleNamespace(consume_clearance=AsyncMock(return_value=False))
        with patch.object(
            inventory, "slot_occupied", AsyncMock(side_effect=TimeoutError())
        ) as probe:
            with self.assertRaises(inventory.InsertionBlocked):
                await inventory.insert_owned_pin(object(), keypad, 2, "1234", manager)
        probe.assert_awaited_once()
        keypad.insert.assert_not_awaited()

    async def test_direct_service_without_manager_cannot_skip_occupied_slot(self):
        keypad = SimpleNamespace(insert=AsyncMock())
        with patch.object(inventory, "slot_occupied", AsyncMock(return_value=True)):
            with self.assertRaises(inventory.InsertionBlocked):
                await inventory.insert_owned_pin(object(), keypad, 2, "1234")
        keypad.insert.assert_not_awaited()

    async def test_failure_persisting_proof_prevents_insertion(self):
        keypad = SimpleNamespace(insert=AsyncMock())
        manager = SimpleNamespace(
            consume_clearance=AsyncMock(side_effect=OSError("store unavailable"))
        )
        with patch.object(inventory, "slot_occupied", AsyncMock()) as probe:
            with self.assertRaises(OSError):
                await inventory.insert_owned_pin(object(), keypad, 2, "1234", manager)
        keypad.insert.assert_not_awaited()
        probe.assert_not_awaited()

    # ------------------------------------------------------------------ #
    # SlotReadError: structure and ValueError compatibility               #
    # ------------------------------------------------------------------ #

    def test_slot_read_error_is_value_error_subclass(self):
        exc = inventory.SlotReadError("TIMEOUT")
        self.assertIsInstance(exc, ValueError)
        self.assertIsInstance(exc, inventory.SlotReadError)

    def test_slot_read_error_carries_fixed_code_and_numeric_fields(self):
        exc = inventory.SlotReadError(
            inventory.SlotReadError.CODE_RESULT_NONZERO,
            result=3,
            frame_length=18,
            echo_match=True,
        )
        self.assertEqual(exc.code, "RESULT_NONZERO")
        self.assertEqual(exc.result, 3)
        self.assertEqual(exc.frame_length, 18)
        self.assertIs(exc.echo_match, True)
        # str() must be exactly the code; no raw frame or credential content.
        self.assertEqual(str(exc), "RESULT_NONZERO")
        self.assertEqual(exc.args, ("RESULT_NONZERO",))

    async def test_slot_read_error_blocks_insertion_caught_as_value_error(self):
        """insert_owned_pin's ValueError catch must accept SlotReadError."""
        keypad = SimpleNamespace(insert=AsyncMock())
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_TIMEOUT
                )
            ),
        ):
            with self.assertRaises(inventory.InsertionBlocked):
                await inventory.insert_owned_pin(object(), keypad, 2, "1234")
        keypad.insert.assert_not_awaited()

    # ------------------------------------------------------------------ #
    # Result-before-echo ordering                                         #
    # ------------------------------------------------------------------ #

    async def test_nonzero_result_with_bad_echo_raises_result_nonzero(self):
        """When result!=0 and echo is also wrong, RESULT_NONZERO fires (not ECHO_MISMATCH)
        and echo_match reflects the actual echo state (False here)."""
        lock = self.lock(slot=3, result=5)  # echo=3 != slot=2; result=5
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        exc = ctx.exception
        self.assertEqual(exc.code, inventory.SlotReadError.CODE_RESULT_NONZERO)
        self.assertEqual(exc.result, 5)
        self.assertIs(exc.echo_match, False)  # echo was wrong, preserved in field
        self.assertEqual(exc.frame_length, 18)

    async def test_zero_result_with_bad_echo_raises_echo_mismatch(self):
        """When result==0 but echo is wrong, ECHO_MISMATCH fires with echo_match=False."""
        lock = self.lock(slot=99, result=0)
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        exc = ctx.exception
        self.assertEqual(exc.code, inventory.SlotReadError.CODE_ECHO_MISMATCH)
        self.assertEqual(exc.result, 0)
        self.assertIs(exc.echo_match, False)

    # ------------------------------------------------------------------ #
    # Mismatched echo never returns empty                                 #
    # ------------------------------------------------------------------ #

    async def test_mismatched_echo_never_returns_empty(self):
        """Wrong slot echo on an all-FF field must not be classified as empty."""
        lock = self.lock(slot=99, field=b"\xff" * 7, result=0)
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        exc = ctx.exception
        self.assertEqual(exc.code, inventory.SlotReadError.CODE_ECHO_MISMATCH)
        self.assertIs(exc.echo_match, False)

    # ------------------------------------------------------------------ #
    # PIN length validation (4–6 digits)                                  #
    # ------------------------------------------------------------------ #

    async def test_four_digit_pin_is_occupied(self):
        lock = self.lock(field=bytes.fromhex("1234ffffffffff"))
        self.assertIs(await inventory.slot_occupied(lock, 2), True)

    async def test_five_digit_pin_is_occupied(self):
        """Odd-length PIN (5 digits) with trailing F nibble must be accepted."""
        # "12345" BCD: nibbles 1,2,3,4,5,F → bytes 0x12,0x34,0x5F then 4×0xFF
        # field hex = "12345fffffffff" (14 chars = 7 bytes)
        lock = self.lock(field=bytes.fromhex("12345fffffffff"))
        self.assertIs(await inventory.slot_occupied(lock, 2), True)

    async def test_six_digit_pin_is_occupied(self):
        # "123456" BCD: bytes 0x12,0x34,0x56 then 4×0xFF
        lock = self.lock(field=bytes.fromhex("123456ffffffff"))
        self.assertIs(await inventory.slot_occupied(lock, 2), True)

    async def test_three_digit_pin_is_malformed(self):
        """PINs shorter than 4 digits must be rejected as malformed."""
        # "123" BCD: nibbles 1,2,3,F → bytes 0x12,0x3F then 5×0xFF
        lock = self.lock(field=bytes.fromhex("123fffffffffff"))
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        self.assertEqual(ctx.exception.code, inventory.SlotReadError.CODE_MALFORMED)

    async def test_seven_digit_pin_is_malformed(self):
        """PINs longer than 6 digits must be rejected as malformed."""
        # "1234567" BCD: nibbles 1,2,3,4,5,6,7,F → bytes 0x12,0x34,0x56,0x7F then 3×0xFF
        lock = self.lock(field=bytes.fromhex("1234567fffffff"))
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        self.assertEqual(ctx.exception.code, inventory.SlotReadError.CODE_MALFORMED)

    # ------------------------------------------------------------------ #
    # Strict empty: only all-FF qualifies                                 #
    # ------------------------------------------------------------------ #

    async def test_strict_empty_all_ff_only(self):
        lock = self.lock(field=b"\xff" * 7)
        self.assertFalse(await inventory.slot_occupied(lock, 2))

    async def test_non_ff_single_byte_is_malformed_not_empty(self):
        """Leading 0x00 byte followed by FF padding is malformed, not empty."""
        # hex "00" + "ff"*6 → rstrip('f') = "00", len=2 → MALFORMED
        lock = self.lock(field=b"\x00" + b"\xff" * 6)
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        self.assertEqual(ctx.exception.code, inventory.SlotReadError.CODE_MALFORMED)

    # ------------------------------------------------------------------ #
    # Matcher behaviour: BB39 only, AA39 observed but rejected            #
    # ------------------------------------------------------------------ #

    async def test_matcher_rejects_aa39_and_accepts_bb39(self):
        """Matcher must return False for AA39 (keep waiting) and True for BB39."""
        lock = self.lock()
        await inventory.slot_occupied(lock, 2)
        _, _, matcher = lock.session.execute.await_args.args

        aa39 = bytearray(18)
        aa39[0:2] = b"\xaa\x39"
        self.assertFalse(matcher(aa39))  # AA39: not accepted; execute keeps waiting

        bb39 = bytearray(18)
        bb39[0:2] = b"\xbb\x39"
        self.assertTrue(matcher(bb39))  # BB39: accepted

        self.assertFalse(matcher(bytearray(18)))  # All-zero: rejected

    async def test_aa39_sets_ack_seen_and_timeout_preserves_it(self):
        """AA39 observed before a timeout must result in ack_seen=True."""

        async def execute_ack_then_timeout(command, name, matcher):
            aa39 = bytearray(18)
            aa39[0:2] = b"\xaa\x39"
            matcher(aa39)  # side-effect: sets ack_seen = True in closure
            raise TimeoutError()  # native execute timeout fires

        lock = self.lock()
        lock.session.execute = execute_ack_then_timeout
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        exc = ctx.exception
        self.assertEqual(exc.code, inventory.SlotReadError.CODE_TIMEOUT)
        self.assertIs(exc.ack_seen, True)

    async def test_timeout_without_aa39_has_ack_seen_false(self):
        """Timeout with no AA39 observation must have ack_seen=False."""

        async def execute_timeout(command, name, matcher):
            raise TimeoutError()

        lock = self.lock()
        lock.session.execute = execute_timeout
        with self.assertRaises(inventory.SlotReadError) as ctx:
            await inventory.slot_occupied(lock, 2)
        exc = ctx.exception
        self.assertEqual(exc.code, inventory.SlotReadError.CODE_TIMEOUT)
        self.assertIs(exc.ack_seen, False)

    # ------------------------------------------------------------------ #
    # discover_slots: diagnostic dict                                     #
    # ------------------------------------------------------------------ #

    async def test_disconnected_code_and_fields_in_diagnostic(self):
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_DISCONNECTED
                )
            ),
        ):
            result = await inventory.discover_slots(object(), 2)
        self.assertFalse(result["complete"])
        diag = result["diagnostic"]
        self.assertEqual(diag["code"], "DISCONNECTED")
        self.assertEqual(diag["exception_class"], "SlotReadError")
        self.assertEqual(diag["slot"], 1)
        self.assertEqual(diag["stage"], "slot_read")
        self.assertIsNone(diag["result"])
        self.assertIsNone(diag["frame_length"])
        self.assertIsNone(diag["echo_match"])

    async def test_timeout_code_and_fields_in_diagnostic(self):
        with patch.object(
            inventory, "slot_occupied", AsyncMock(side_effect=TimeoutError())
        ):
            result = await inventory.discover_slots(object(), 2)
        self.assertFalse(result["complete"])
        diag = result["diagnostic"]
        self.assertEqual(diag["code"], "TIMEOUT")
        self.assertEqual(diag["exception_class"], "TimeoutError")
        self.assertIsNone(diag["result"])
        self.assertIsNone(diag["frame_length"])
        self.assertIsNone(diag["echo_match"])

    async def test_acknowledgement_is_diagnostic_not_empty_slot_evidence(self):
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(side_effect=inventory.SlotReadError("TIMEOUT", ack_seen=True)),
        ):
            result = await inventory.discover_slots(object(), 1)
        self.assertEqual(result["slots"], [{"slot": 1, "state": "unknown"}])
        self.assertIs(result["diagnostic"]["ack_seen"], True)

    async def test_timeout_distinguishes_unrelated_notification_without_exposing_frame(
        self,
    ):
        lock = self.lock(field=bytes.fromhex("271828ffffffff"))
        lock.session._last_callback_time = 1.0

        async def execute(command, name, matcher):
            unrelated = bytearray(lock.session.execute.return_value)
            unrelated[1] = 0x02
            self.assertFalse(matcher(unrelated))
            lock.session._last_callback_time = 2.0
            raise TimeoutError()

        lock.session.execute.side_effect = execute
        result = await inventory.discover_slots(lock, 1)
        self.assertEqual(result["diagnostic"]["response_opcodes"], [2])
        self.assertIs(result["diagnostic"]["notifications_seen"], True)
        self.assertEqual(result["slots"], [{"slot": 1, "state": "unknown"}])
        self.assertNotIn("271828", str(result))

    async def test_single_slot_probe_does_not_start_at_slot_one(self):
        with patch.object(
            inventory, "slot_occupied", AsyncMock(return_value=True)
        ) as read:
            result = await inventory.discover_slots(
                object(), 1, start_slot=26, maximum_slot=26
            )
        self.assertEqual(read.await_args.args[1], 26)
        read.assert_awaited_once()
        self.assertEqual(result["slots"], [{"slot": 26, "state": "occupied"}])

    async def test_invalid_probe_range_sends_no_read(self):
        for start, end in ((0, 1), (1, 256), (26, 25), (True, 1), (1, "26")):
            with patch.object(inventory, "slot_occupied", AsyncMock()) as read:
                with self.assertRaises(ValueError):
                    await inventory.discover_slots(
                        object(), 1, start_slot=start, maximum_slot=end
                    )
                read.assert_not_awaited()

    async def test_disconnected_vs_timeout_diagnostic_code_differs(self):
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_DISCONNECTED
                )
            ),
        ):
            disc = await inventory.discover_slots(object(), 2)

        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_TIMEOUT
                )
            ),
        ):
            tout = await inventory.discover_slots(object(), 2)

        self.assertEqual(disc["diagnostic"]["code"], "DISCONNECTED")
        self.assertEqual(tout["diagnostic"]["code"], "TIMEOUT")
        self.assertNotEqual(disc["diagnostic"]["code"], tout["diagnostic"]["code"])

    async def test_result_nonzero_diagnostic_includes_numeric_fields(self):
        """Diagnostic dict must carry result/frame_length/echo_match from SlotReadError."""
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_RESULT_NONZERO,
                    result=7,
                    frame_length=18,
                    echo_match=True,
                )
            ),
        ):
            result = await inventory.discover_slots(object(), 2)
        diag = result["diagnostic"]
        self.assertEqual(diag["code"], "RESULT_NONZERO")
        self.assertEqual(diag["result"], 7)
        self.assertEqual(diag["frame_length"], 18)
        self.assertIs(diag["echo_match"], True)

    async def test_echo_mismatch_diagnostic_echo_match_is_false(self):
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_ECHO_MISMATCH,
                    result=0,
                    frame_length=18,
                    echo_match=False,
                )
            ),
        ):
            result = await inventory.discover_slots(object(), 2)
        diag = result["diagnostic"]
        self.assertEqual(diag["code"], "ECHO_MISMATCH")
        self.assertIs(diag["echo_match"], False)
        self.assertEqual(diag["result"], 0)

    # ------------------------------------------------------------------ #
    # Diagnostic reason: safe content only, no raw credentials            #
    # ------------------------------------------------------------------ #

    async def test_diagnostic_reason_contains_only_code_and_numerics(self):
        """Reason string must be assembled from fixed codes and numeric values."""
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_RESULT_NONZERO,
                    result=7,
                    frame_length=18,
                    echo_match=True,
                )
            ),
        ):
            result = await inventory.discover_slots(object(), 2)
        reason = result["reason"]
        self.assertIn("RESULT_NONZERO", reason)
        self.assertIn("slot=1", reason)
        self.assertIn("result=7", reason)
        self.assertIn("length=18", reason)
        self.assertEqual(reason, result["diagnostic"]["reason"])

    async def test_no_raw_credential_in_malformed_diagnostic_reason(self):
        """MALFORMED reason has fixed prose and metadata, never credential bytes."""
        with patch.object(
            inventory,
            "slot_occupied",
            AsyncMock(
                side_effect=inventory.SlotReadError(
                    inventory.SlotReadError.CODE_MALFORMED,
                    frame_length=18,
                    echo_match=True,
                )
            ),
        ):
            result = await inventory.discover_slots(object(), 2)
        reason = result["reason"]
        self.assertIn("MALFORMED", reason)
        self.assertIn("slot=1", reason)
        self.assertEqual(
            reason,
            "Slot 1 response did not contain valid occupancy data (MALFORMED slot=1 length=18).",
        )

    def test_slot_read_error_message_is_only_code(self):
        """SlotReadError str() must be exactly the code."""
        exc = inventory.SlotReadError(
            inventory.SlotReadError.CODE_MALFORMED,
            frame_length=18,
            echo_match=True,
        )
        self.assertEqual(str(exc), "MALFORMED")
        self.assertEqual(exc.args, ("MALFORMED",))


if __name__ == "__main__":
    unittest.main()
