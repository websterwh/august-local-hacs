"""Synthetic protocol frames only; never connect to hardware."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

spec = importlib.util.spec_from_file_location(
    "keypad_protocol_under_test",
    Path(__file__).resolve().parents[1] / "custom_components/august_local/protocol.py",
)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


def frame(marker=0xBB, opcode=0x29, result=0):
    value = bytearray(18)
    value[0], value[1], value[15] = marker, opcode, result
    return value


def command(opcode):
    value = bytearray(18)
    value[0], value[1], value[16] = 0xEE, opcode, 2
    return value


class ClearAllProtocolTests(unittest.IsolatedAsyncioTestCase):
    def keypad(self, reply):
        async def execute(request, name, matches):
            if not matches(reply):
                raise TimeoutError()
            return reply

        session = SimpleNamespace(
            build_command=command, execute=AsyncMock(side_effect=execute)
        )
        return protocol.ASL05Keypad(SimpleNamespace(session=session)), session

    async def test_clear_all_sends_only_zero_payload_opcode_29(self):
        keypad, session = self.keypad(frame())
        await keypad.clear_all()
        session.execute.assert_awaited_once()
        request, name, _ = session.execute.await_args.args
        self.assertEqual(request[0:2], bytes([0xEE, 0x29]))
        self.assertEqual(request[4:16], bytes(12))
        self.assertEqual(request[16:18], bytes([2, 0]))
        self.assertEqual(name, "asl05_keypad_29")

    async def test_ack_is_not_clear_confirmation_and_is_never_retried(self):
        keypad, session = self.keypad(frame(marker=0xAA))
        with self.assertRaisesRegex(protocol.KeypadFailure, "outcome unknown"):
            await keypad.clear_all()
        session.execute.assert_awaited_once()
        self.assertFalse(keypad._transaction.locked())

    async def test_ack_then_result_waits_for_result(self):
        keypad, session = self.keypad(frame())

        async def execute(request, name, matches):
            self.assertFalse(matches(frame(marker=0xAA)))
            self.assertTrue(matches(frame()))
            return frame()

        session.execute.side_effect = execute
        await keypad.clear_all()
        session.execute.assert_awaited_once()

    async def test_nonzero_result_stops_without_other_commands(self):
        keypad, session = self.keypad(frame(result=2))
        with self.assertRaisesRegex(protocol.KeypadFailure, "Opcode 29: result 2"):
            await keypad.clear_all()
        session.execute.assert_awaited_once()

    async def test_wrong_opcode_cannot_confirm_clear(self):
        keypad, session = self.keypad(frame(opcode=0x28))
        with self.assertRaises(protocol.KeypadFailure):
            await keypad.clear_all()
        session.execute.assert_awaited_once()

    async def test_broken_session_returning_ack_is_still_rejected(self):
        keypad, session = self.keypad(frame())
        session.execute.side_effect = None
        session.execute.return_value = frame(marker=0xAA)
        with self.assertRaisesRegex(protocol.KeypadFailure, "malformed response"):
            await keypad.clear_all()

    async def test_clear_all_does_not_run_without_authenticated_session(self):
        keypad = protocol.ASL05Keypad(SimpleNamespace(session=None))
        with self.assertRaisesRegex(protocol.KeypadFailure, "Not authenticated"):
            await keypad.clear_all()
