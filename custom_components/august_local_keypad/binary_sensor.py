"""Phone proximity restricted to a selected door Bluetooth adapter."""
import time
from homeassistant.components import bluetooth
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from . import DOMAIN
from .nearby import NearGate, matches_beacon

async def async_setup_entry(hass, entry, async_add_entities):
    entities = {}
    @callback
    def add(sensor, profile):
        if sensor in entities:
            entities[sensor].configure(profile)
        else:
            entity = PhoneNearDoor(entry, sensor, profile)
            entities[sensor] = entity
            async_add_entities([entity])
    hass.data[DOMAIN]['nearby_add'] = add
    for sensor, profile in entry.options.get('nearby_profiles', {}).items():
        add(sensor, profile)

class PhoneNearDoor(BinarySensorEntity):
    _attr_should_poll = False
    _attr_icon = 'mdi:bluetooth-connect'
    def __init__(self, entry, sensor, profile):
        self._attr_unique_id = f'{entry.entry_id}_{sensor}_near_door'
        self._attr_name = f"{profile['name']} near door"
        self.profile = profile
        self.gate = NearGate(profile['threshold'])
        self._attr_is_on = False
        self.last_seen = None
        self.rssi = None
        self._expiry = None
        self._addresses = {}
    @property
    def extra_state_attributes(self):
        return {'last_seen':self.last_seen, 'rssi':self.rssi,
                'threshold':self.profile['threshold'], 'receiver':self.profile['source']}
    @callback
    def configure(self, profile):
        self.profile = profile
        self.gate = NearGate(profile['threshold'])
        self._attr_is_on = False
        self.last_seen = None
        self.rssi = None
        self.async_write_ha_state()
    async def async_added_to_hass(self):
        self.async_on_remove(bluetooth.async_register_callback(self.hass, self._discovery,
            {'manufacturer_id':0x004C, 'connectable':False}, bluetooth.BluetoothScanningMode.PASSIVE))
        self.async_on_remove(self._cleanup)
    @callback
    def _discovery(self, info, change):
        if not matches_beacon(info.manufacturer_data, self.profile): return
        if info.address not in self._addresses:
            if len(self._addresses) >= 16:
                _, cancel = self._addresses.popitem(); cancel()
            self._addresses[info.address] = bluetooth.async_register_advertisement_callback(self.hass, self._advertisement, info.address)
        self._advertisement(info)
    @callback
    def _advertisement(self, info):
        if info.source != self.profile['source'] or not matches_beacon(info.manufacturer_data, self.profile): return
        if not self.gate.sample(info.time, info.rssi, time.monotonic()): return
        self.rssi = info.rssi
        self.last_seen = dt_util.utcnow().isoformat()
        self._attr_is_on = self.gate.near
        if self._expiry: self._expiry()
        self._expiry = async_call_later(self.hass, 10, self._expire)
        self.async_write_ha_state()
    @callback
    def _expire(self, _):
        self._expiry = None
        self.gate.reset()
        self._attr_is_on = False
        self.async_write_ha_state()
    @callback
    def _cleanup(self):
        if self._expiry: self._expiry()
        for cancel in self._addresses.values(): cancel()
        self._addresses.clear()
