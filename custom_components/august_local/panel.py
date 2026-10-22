"""Authenticated local PIN manager API and custom HA panel."""

import asyncio
from pathlib import Path
import re
import time
import traceback
from bleak.exc import BleakError
from yalexs_ble.session import DisconnectedError
from homeassistant.components import panel_custom, frontend, bluetooth
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.helpers.storage import Store
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError
from .manager import PinManager, ManagerError, InsertRejected, InsertNotStarted
from . import DOMAIN, _private_protocol_logs


async def setup_panel(hass, entry):
    store = Store(hass, 1, f"{DOMAIN}.registry")
    state = await store.async_load()
    if state is None:
        state = {"records": {}}
        old = entry.options.get("pins", {}).get("slot_29")
        if old:
            state["records"]["29"] = {
                "slot": 29,
                "name": "Local slot 29",
                "owner_id": None,
                "source": "local",
                "status": "active",
                "access_type": "always",
                "pin": old,
            }
        await store.async_save(state)

    async def operate(operation, slot, pin, previous):
        options = dict(entry.options)
        refs = dict(options.get("pins", {}))
        refs.update(_manager_new=pin, _manager_previous=previous)
        options.update(
            pins=refs, manager_slots=[r["slot"] for r in state["records"].values()]
        )
        hass.config_entries.async_update_entry(entry, options=options)
        data = {"slot": slot, "pin_reference": "_manager_new"}
        if operation == "program":
            data["previous_pin_reference"] = "_manager_previous"
        # Authorization has been enforced by the manager on this authenticated
        # request; no PIN values are in service data or traces.
        try:
            await hass.services.async_call(DOMAIN, operation, data, blocking=True)
        except Exception as exc:
            if operation == "insert" and str(exc) in (
                "Slot occupancy could not be confirmed; no PIN insertion sent",
                "Slot is occupied; no PIN insertion sent",
            ):
                raise InsertNotStarted() from None
            # A received nonzero result is a definite rejection, unlike a
            # timeout. Never clear a duplicate PIN after a rejected insertion.
            if operation == "insert" and re.fullmatch(
                r"Opcode (27|2b|2c): result [1-9][0-9]*", str(exc)
            ):
                raise InsertRejected() from None
            raise
        finally:
            refs.pop("_manager_new", None)
            refs.pop("_manager_previous", None)
            options["pins"] = refs
            hass.config_entries.async_update_entry(entry, options=options)

    async def discover(limit):
        from .inventory import discover_slots

        ble_entry = hass.config_entries.async_get_entry(entry.data["entry_id"])
        runtime = getattr(ble_entry, "runtime_data", None) if ble_entry else None
        push = getattr(runtime, "lock", None)
        if (
            ble_entry is None
            or ble_entry.domain != "yalexs_ble"
            or push is None
            or not getattr(push, "_running", False)
        ):
            raise ManagerError(
                "The configured Yale Access Bluetooth lock is not loaded"
            )
        try:
            await asyncio.wait_for(push._operation_lock.acquire(), 20)
        except TimeoutError:
            raise ManagerError("Bluetooth is busy; no occupancy probe sent") from None
        try:
            with _private_protocol_logs():
                lock = await asyncio.wait_for(push._ensure_connected(), 45)
                push._cancel_future_update()
                try:
                    return await discover_slots(lock, limit)
                finally:
                    push._complete_operation(time.monotonic())
        except (DisconnectedError, BleakError, TimeoutError):
            raise ManagerError(
                "Bluetooth disconnected or timed out during read-only slot discovery. No PIN write was sent. Close other lock apps and check the proxy connection before trying discovery again."
            ) from None
        finally:
            push._operation_lock.release()

    manager = PinManager(state, store.async_save, operate, discover=discover)
    await store.async_save(state)
    hass.data.setdefault(DOMAIN, {})["manager"] = manager
    hass.data[DOMAIN]["entry"] = entry
    if not hass.data[DOMAIN].get("panel_registered"):
        hass.http.register_view(ManagerView())
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/august-local-keypad/panel.js",
                    str(Path(__file__).parent / "panel.js"),
                    False,
                )
            ]
        )
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path="august-local-keypad",
            webcomponent_name="august-pin-manager-v23",
            sidebar_title="Door PINs",
            sidebar_icon="mdi:dialpad",
            module_url="/august-local-keypad/panel.js?v=23",
        )
        hass.data[DOMAIN]["panel_registered"] = True


class ManagerView(HomeAssistantView):
    url = "/api/august_local_keypad/manage"
    name = "api:august_local_keypad:manage"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        user = request["hass_user"]
        manager = hass.data.get(DOMAIN, {}).get("manager")
        if manager is None or not user.is_active:
            return self.json({"error": "Manager unavailable"}, status_code=503)
        users = []
        if user.is_admin:
            users = [
                {"id": u.id, "name": u.name or "Unnamed user"}
                for u in await hass.auth.async_get_users()
                if u.is_active and not u.system_generated
            ]
        result = {
            "admin": user.is_admin,
            "records": manager.listing(user),
            "users": users,
            "pin_scheduling": False,
            "pin_schedule_reason": "Day/time restrictions are not yet verified on this lock. Manage scheduled codes in the August app; HA timers are not used to simulate security restrictions.",
        }
        if user.is_admin:
            entry = hass.data[DOMAIN]["entry"]
            registry = er.async_get(hass)
            result["locks"] = [
                {
                    "entity_id": e.entity_id,
                    "name": (
                        hass.states.get(e.entity_id).name
                        if hass.states.get(e.entity_id)
                        else e.entity_id
                    ),
                }
                for e in er.async_entries_for_config_entry(
                    registry, entry.data["entry_id"]
                )
                if e.domain == "lock"
                and not e.disabled_by
                and "secure_mode" not in e.entity_id
            ]
            result["receivers"] = [
                {
                    "source": scanner.source,
                    "name": getattr(scanner, "name", scanner.source),
                }
                for scanner in bluetooth.async_current_scanners(hass)
            ]
            result["nearby_profiles"] = [
                {
                    "sensor": sensor,
                    "name": p["name"],
                    "source": p["source"],
                    "threshold": p["threshold"],
                    "entity_id": registry.async_get_entity_id(
                        "binary_sensor", DOMAIN, f"{entry.entry_id}_{sensor}_near_door"
                    ),
                }
                for sensor, p in entry.options.get("nearby_profiles", {}).items()
            ]
            result["arrival_prefix"] = f"door_pins_arrival_{entry.entry_id}"
        return self.json(result)

    async def post(self, request):
        hass = request.app["hass"]
        user = request["hass_user"]
        manager = hass.data.get(DOMAIN, {}).get("manager")
        if manager is None or not user.is_active:
            return self.json({"error": "Manager unavailable"}, status_code=503)
        try:
            data = await request.json()
            action = data.get("action")
            if {
                "schedule",
                "access_type",
                "access_times",
                "days",
                "start_time",
                "end_time",
            } & data.keys():
                raise ManagerError(
                    "Lock-enforced PIN scheduling is not verified; no PIN change sent. Use the August app for scheduled access."
                )
            if action == "nearby_save":
                manager.admin(user)
                from .nearby import beacon_identity

                entry = hass.data[DOMAIN]["entry"]
                sensor = data.get("sensor")
                entity = (
                    er.async_get(hass).async_get(sensor)
                    if isinstance(sensor, str)
                    else None
                )
                state = hass.states.get(sensor) if entity else None
                if (
                    state is None
                    or entity.platform != "mobile_app"
                    or "ble_transmitter" not in sensor
                ):
                    raise ManagerError("Choose the Companion BLE Transmitter sensor")
                source = data.get("source")
                if source not in {
                    scanner.source for scanner in bluetooth.async_current_scanners(hass)
                }:
                    raise ManagerError(
                        "Choose an active Bluetooth receiver at the door"
                    )
                threshold = data.get("threshold")
                if type(threshold) is not int or not -90 <= threshold <= -30:
                    raise ManagerError(
                        "Signal threshold must be between -90 and -30 dBm"
                    )
                identity, major, minor = beacon_identity(state.attributes)
                profile = {
                    "uuid": identity,
                    "major": major,
                    "minor": minor,
                    "source": source,
                    "threshold": threshold,
                    "name": state.name.removesuffix(" BLE Transmitter").removesuffix(
                        " BLE transmitter"
                    ),
                }
                async with manager.lock:
                    options = dict(entry.options)
                    profiles = dict(options.get("nearby_profiles", {}))
                    profiles[sensor] = profile
                    options["nearby_profiles"] = profiles
                    hass.config_entries.async_update_entry(entry, options=options)
                    add = hass.data[DOMAIN].get("nearby_add")
                    if add is None:
                        raise ManagerError("Nearby detection platform is not ready")
                    add(sensor, profile)
                return self.json({"ok": True})
            if action in ("auto_lock_read", "auto_lock_save"):
                manager.admin(user)
                from .auto_lock import operate as auto_lock_operate

                return self.json(await auto_lock_operate(hass, data))
            if action == "import":
                manager.admin(user)
                codes = await cloud_codes(hass)
                result = await manager.import_codes(user, codes)
                return self.json({"ok": True, **result})
            if action == "provision":
                manager.admin(user)
                users = await hass.auth.async_get_users()
                result = await manager.provision(user, users, data.get("count"))
                return self.json({"ok": True, **result})
            if action == "create":
                slot = await manager.create(user, data.get("pin"), data.get("name", ""))
                return self.json({"ok": True, "slot": slot})
            slot = data.get("slot")
            if type(slot) is not int or not 1 <= slot <= 255:
                raise ManagerError("Invalid slot")
            if action == "assign":
                manager.admin(user)
                owner = data.get("owner_id") or None
                if owner:
                    target = await hass.auth.async_get_user(owner)
                    if (
                        target is None
                        or not target.is_active
                        or target.system_generated
                    ):
                        raise ManagerError("Select an active HA user")
                await manager.assign(user, slot, owner, str(data.get("name", "")))
            elif action == "reveal":
                record = manager.record(user, slot)
                return self.json(
                    {"pin": record.get("pin") or record.get("pending_pin", "")}
                )
            elif action in ("program", "delete"):
                await manager.mutate(user, slot, action, data.get("pin"))
            else:
                raise ManagerError("Invalid action")
        except (ManagerError, ValueError) as exc:
            return self.json({"error": str(exc)}, status_code=400)
        except HomeAssistantError as exc:
            return self.json({"error": str(exc)}, status_code=400)
        except Exception as exc:
            frames = traceback.extract_tb(exc.__traceback__)
            frame = frames[-1]
            detail = (
                f"{type(exc).__name__} at {Path(frame.filename).name}:{frame.lineno}"
            )
            return self.json(
                {
                    "error": f"Operation unavailable ({detail}); no sensitive details returned"
                },
                status_code=400,
            )
        return self.json({"ok": True})


async def cloud_codes(hass):
    """Read only the configured lock's loaded cloud codes; never log payloads."""
    entry = hass.data[DOMAIN]["entry"]
    ble = hass.config_entries.async_get_entry(entry.data["entry_id"])
    address = str(ble.data.get("address", "")).replace(":", "").lower()
    if not address:
        raise ManagerError("Cannot identify the configured lock")
    entries = hass.config_entries.async_entries("august")
    loaded = 0
    devices = 0
    with _private_protocol_logs():
        for cloud in entries:
            runtime = getattr(cloud, "runtime_data", None)
            if runtime is None:
                continue
            loaded += 1
            gateway = runtime._gateway
            token = await gateway.async_get_access_token()
            # HA removes Bluetooth-only locks from its runtime device cache
            # when no August Connect bridge is attached. Read the account's
            # lock list and details directly; never wake or operate a lock.
            locks = await runtime._api.async_get_operable_locks(token) or []
            devices += len(locks)
            for lock in locks:
                lock_id = lock.device_id
                detail = await runtime._api.async_get_lock_detail(token, lock_id)
                mac = str(getattr(detail, "mac_address", "")).replace(":", "").lower()
                if mac != address:
                    continue
                pins = await runtime._api.async_get_pins(token, lock_id)
                return [
                    {
                        "slot": int(p.slot),
                        "pin": str(p.pin),
                        "name": " ".join(filter(None, [p.first_name, p.last_name])),
                        "access_type": str(p.access_type),
                    }
                    for p in pins
                ]
    if not entries:
        raise ManagerError(
            "Connect the official August integration in HA before importing. Local management works without it."
        )
    if not loaded:
        raise ManagerError(
            "The August account is configured but has not loaded. Check its integration setup or authentication error, then retry."
        )
    if not devices:
        raise ManagerError(
            "August is connected but returned no locks for this account. Check that the signed-in August account owns or can access the front-door lock and authorized it for Home Assistant."
        )
    raise ManagerError(
        "August is connected, but none of its returned devices matches this lock’s Bluetooth address. Check the August account and lock selected in the local integration."
    )
