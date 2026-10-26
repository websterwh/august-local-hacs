"""Synthetic proximity tests; no Bluetooth, network, or lock operations."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "august_local"
PACKAGE = "_august_nearby_tests"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


package = ModuleType(PACKAGE)
package.__path__ = []
package.DOMAIN = "august_local"
bluetooth = ModuleType("homeassistant.components.bluetooth")
bluetooth.async_register_advertisement_callback = Mock(side_effect=lambda *args: Mock())
components = ModuleType("homeassistant.components")
components.bluetooth = bluetooth
binary = ModuleType("homeassistant.components.binary_sensor")
binary.BinarySensorEntity = type(
    "BinarySensorEntity", (), {"async_write_ha_state": lambda self: None}
)
core = ModuleType("homeassistant.core")
core.callback = lambda fn: fn
event = ModuleType("homeassistant.helpers.event")
event.async_call_later = Mock(side_effect=lambda *args: Mock())
util = ModuleType("homeassistant.util")
util.dt = SimpleNamespace(utcnow=Mock())
with patch.dict(
    sys.modules,
    {
        PACKAGE: package,
        "homeassistant": ModuleType("homeassistant"),
        "homeassistant.components": components,
        "homeassistant.components.bluetooth": bluetooth,
        "homeassistant.components.binary_sensor": binary,
        "homeassistant.core": core,
        "homeassistant.helpers": ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.event": event,
        "homeassistant.util": util,
    },
):
    nearby = load(f"{PACKAGE}.nearby", "nearby.py")
    sensor_module = load(f"{PACKAGE}.binary_sensor", "binary_sensor.py")


PROFILE = {
    "uuid": "12345678-1234-1234-1234-123456789abc",
    "major": 1,
    "minor": 2,
    "threshold": -65,
    "source": "synthetic-door-proxy",
    "name": "Synthetic phone",
}
PAYLOAD = (
    b"\x02\x15"
    + uuid.UUID(PROFILE["uuid"]).bytes
    + PROFILE["major"].to_bytes(2, "big")
    + PROFILE["minor"].to_bytes(2, "big")
    + b"\xc5"
)


class NearGateTests(unittest.TestCase):
    def test_requires_three_samples_and_two_seconds(self):
        gate = nearby.NearGate(-65)
        for timestamp in (100, 100.5, 101):
            self.assertTrue(gate.sample(timestamp, -60, timestamp))
            self.assertFalse(gate.near)
        gate.sample(102, -60, 102)
        self.assertTrue(gate.near)

    def test_threshold_boundary_and_weak_sample_decay(self):
        gate = nearby.NearGate(-65)
        for timestamp in (100, 101, 102):
            gate.sample(timestamp, -65, timestamp)
        self.assertTrue(gate.near)
        self.assertEqual(gate.samples, 3)
        gate.sample(103, -66, 103)
        self.assertEqual(gate.samples, 2)
        gate.sample(104, -66, 104)
        gate.sample(105, -66, 105)
        self.assertFalse(gate.near)
        self.assertEqual(gate.samples, 0)
        gate.sample(106, -60, 106)
        self.assertFalse(gate.near)
        self.assertEqual(gate.samples, 1)

    def test_rejects_stale_future_duplicate_and_out_of_order(self):
        gate = nearby.NearGate(-65)
        self.assertFalse(gate.sample(94, -60, 100))
        self.assertFalse(gate.sample(102, -60, 100))
        self.assertTrue(gate.sample(100, -60, 100))
        self.assertFalse(gate.sample(100, -60, 100))
        self.assertFalse(gate.sample(99, -60, 100))
        self.assertEqual(gate.samples, 1)
        self.assertEqual(gate.last, 100)

    def test_gap_resets_old_strong_samples(self):
        gate = nearby.NearGate(-65)
        for timestamp in (100, 101, 110):
            gate.sample(timestamp, -60, timestamp)
        self.assertFalse(gate.near)
        self.assertEqual(gate.samples, 1)
        for timestamp in (111, 112):
            gate.sample(timestamp, -60, timestamp)
        self.assertTrue(gate.near)
    def test_beacon_must_match_signature_uuid_major_and_minor(self):
        self.assertTrue(nearby.matches_beacon({0x004C: PAYLOAD}, PROFILE))
        for index in (0, 2, 18, 20):
            corrupted = bytearray(PAYLOAD)
            corrupted[index] ^= 1
            with self.subTest(index=index):
                self.assertFalse(
                    nearby.matches_beacon({0x004C: bytes(corrupted)}, PROFILE)
                )
        self.assertFalse(nearby.matches_beacon({0x004C: PAYLOAD[:22]}, PROFILE))
        self.assertFalse(nearby.matches_beacon({0xFFFF: PAYLOAD}, PROFILE))

    def test_identity_parsing_and_bounds(self):
        expected = (PROFILE["uuid"], 1, 2)
        self.assertEqual(
            nearby.beacon_identity({"UUID": PROFILE["uuid"], "Major": 1, "Minor": 2}),
            expected,
        )
        self.assertEqual(
            nearby.beacon_identity({"identifier": f"{PROFILE['uuid']}_1_2"}), expected
        )
        for attributes in (
            {},
            {"uuid": PROFILE["uuid"], "major": -1, "minor": 2},
            {"uuid": PROFILE["uuid"], "major": 1, "minor": 65536},
        ):
            with self.subTest(attributes=attributes), self.assertRaises(ValueError):
                nearby.beacon_identity(attributes)


class SensorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sensor = sensor_module.PhoneNearDoor(
            SimpleNamespace(entry_id="synthetic"), "sensor.synthetic", dict(PROFILE)
        )
        self.sensor.hass = object()
        self.clock = 100
        self.clock_patch = patch.object(
            sensor_module.time, "monotonic", side_effect=lambda: self.clock
        )
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.schedule = patch.object(
            sensor_module, "async_call_later", side_effect=lambda *args: Mock()
        )
        self.timer = self.schedule.start()
        self.addCleanup(self.schedule.stop)
        self.sensor.async_write_ha_state = Mock()
        sensor_module.dt_util.utcnow.return_value = SimpleNamespace(
            isoformat=lambda: "synthetic-time"
        )

    def advertisement(self, timestamp, rssi=-60, source=None, payload=PAYLOAD):
        self.clock = timestamp
        return SimpleNamespace(
            time=timestamp,
            rssi=rssi,
            source=source or PROFILE["source"],
            address="AA:BB:CC:DD:EE:FF",
            manufacturer_data={0x004C: payload},
        )

    def activate(self, start=100):
        for timestamp in range(start, start + 3):
            self.sensor._advertisement(self.advertisement(timestamp))
        self.assertTrue(self.sensor._attr_is_on)

    def test_other_proxy_or_beacon_cannot_update_sensor(self):
        self.sensor._advertisement(self.advertisement(100, source="different-proxy"))
        self.sensor._advertisement(self.advertisement(101, payload=b"unrelated"))
        self.sensor.async_write_ha_state.assert_not_called()
        self.timer.assert_not_called()
        self.assertIsNone(self.sensor.last_seen)

    def test_fresh_samples_activate_and_replace_expiry(self):
        self.sensor._advertisement(self.advertisement(100))
        first_cancel = self.sensor._expiry
        self.sensor._advertisement(self.advertisement(101))
        first_cancel.assert_called_once_with()
        self.sensor._advertisement(self.advertisement(102))
        self.assertTrue(self.sensor._attr_is_on)
        self.assertEqual(self.timer.call_count, 3)
        self.assertEqual(self.timer.call_args.args[1], 10)
        self.assertEqual(self.sensor.extra_state_attributes["rssi"], -60)

    def test_weak_sample_disarms_and_expiry_resets_gate(self):
        self.activate()
        self.sensor._advertisement(self.advertisement(103, rssi=-80))
        self.assertFalse(self.sensor._attr_is_on)
        self.activate(104)
        self.sensor._expire(None)
        self.assertFalse(self.sensor._attr_is_on)
        self.assertEqual(self.sensor.gate.samples, 0)
        self.assertIsNone(self.sensor._expiry)

    def test_duplicate_advertisement_does_not_refresh_expiry(self):
        self.sensor._advertisement(self.advertisement(100))
        self.sensor._advertisement(self.advertisement(100))
        self.assertEqual(self.timer.call_count, 1)

    def test_cleanup_cancels_expiry_and_raw_address_subscription(self):
        cancel = Mock()
        with patch.object(
            sensor_module.bluetooth,
            "async_register_advertisement_callback",
            return_value=cancel,
        ) as register:
            self.sensor._discovery(self.advertisement(100), None)
            self.sensor._discovery(self.advertisement(101), None)
            register.assert_called_once()
        expiry = self.sensor._expiry
        self.sensor._cleanup()
        expiry.assert_called_once_with()
        cancel.assert_called_once_with()
        self.assertEqual(self.sensor._addresses, {})


if __name__ == "__main__":
    unittest.main()
