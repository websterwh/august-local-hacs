"""PIN registry and per-user access policy; never log record contents."""

import asyncio
import copy
import re


class ManagerError(Exception):
    pass


class InsertRejected(ManagerError):
    """Lock definitively rejected insertion; no new credential committed."""


class InsertNotStarted(ManagerError):
    """An insertion was blocked before any PIN-changing command was sent."""


class PinManager:
    def __init__(self, state, save, operate, *, discover=None):
        self.state = state
        self.save = save
        self.operate = operate
        self.discover = discover
        self.lock = asyncio.Lock()
        # Historical range reservations were only metadata, never occupancy proof.
        for key, record in list(state["records"].items()):
            if (
                record.get("source") == "local_reserved"
                and record.get("status") == "reserved"
                and not record.get("pin")
                and not record.get("pending_pin")
            ):
                del state["records"][key]
            elif record.get("source") == "local" and record.get("status") == "active":
                record["status"] = "programmed_unverified"

    @staticmethod
    def reusable(record):
        return (
            not record.get("pin")
            and not record.get("pending_pin")
            and (
                record.get("status") == "cleared"
                or record.get("status") == "reserved"
                and record.get("verified_empty") is True
            )
        )

    @staticmethod
    def admin(user):
        if user is None or not user.is_active or not user.is_admin:
            raise ManagerError("Administrator access required")

    @staticmethod
    def visible(user, record):
        return (
            user is not None
            and user.is_active
            and (user.is_admin or record.get("owner_id") == user.id)
        )

    def record(self, user, slot):
        r = self.state["records"].get(str(slot))
        if r is None or not self.visible(user, r):
            raise ManagerError("This slot is not assigned to you")
        return r

    def listing(self, user):
        return [
            {
                k: r.get(k)
                for k in ("slot", "name", "owner_id", "source", "status", "access_type")
            }
            | {"has_pin": bool(r.get("pin") or r.get("pending_pin"))}
            for r in self.state["records"].values()
            if self.visible(user, r)
        ]

    async def assign(self, user, slot, owner_id, name):
        self.admin(user)
        async with self.lock:
            r = self.record(user, slot)
            if r.get("pending_pin"):
                raise ManagerError(
                    "Resolve the pending operation before changing ownership"
                )
            r.update(owner_id=owner_id, name=name[:80])
            await self.save(copy.deepcopy(self.state))

    async def provision(self, user, users, count=None):
        self.admin(user)
        people = {u.id: u for u in users if u.is_active and not u.system_generated}
        automatic = count is None
        target = len(people) if automatic else count
        if type(target) is not int or not 1 <= target <= 50:
            raise ManagerError(
                "Choose total capacity between 1 and 50, or add an active personal HA user"
            )
        async with self.lock:
            records = copy.deepcopy(self.state["records"])
            capacity = [
                r
                for r in records.values()
                if r.get("source") != "august_import"
                and (self.reusable(r) or r.get("status") == "programmed_unverified")
            ]
            assigned = {
                r.get("owner_id") for r in capacity if r.get("owner_id") in people
            }
            missing_users = (
                [u for uid, u in people.items() if uid not in assigned]
                if automatic
                else []
            )
            available = [
                r for r in capacity if self.reusable(r) and r.get("owner_id") is None
            ]
            needed = (
                max(0, len(missing_users) - len(available))
                if automatic
                else max(0, target - len(capacity))
            )
            discovery = {"complete": False, "reason": None}
            allocated = 0
            if needed:
                if self.discover is None:
                    raise ManagerError(
                        "Read-only slot discovery is unavailable; no slots allocated"
                    )
                discovery = await self.discover(50)
                # Duplicate or contradictory scan entries must not create free slots.
                seen = {}
                for item in discovery.get("slots", []):
                    slot, status = item.get("slot"), item.get("state")
                    if type(slot) is int and 1 <= slot <= 255:
                        seen[slot] = status if slot not in seen else "unknown"
                for slot in sorted(seen):
                    existing = records.get(str(slot))
                    recoverable = (
                        existing is not None
                        and existing.get("source") == "local_discovered"
                        and existing.get("status") == "reserved"
                        and not existing.get("pin")
                        and not existing.get("pending_pin")
                        and not self.reusable(existing)
                    )
                    if (
                        seen[slot] != "empty"
                        or existing is not None
                        and not recoverable
                    ):
                        continue
                    record = {
                        "slot": slot,
                        "name": f"Available slot {slot}",
                        "owner_id": None,
                        "source": "local_discovered",
                        "status": "reserved",
                        "access_type": "always",
                        "verified_empty": True,
                    }
                    if existing:
                        record.update(
                            owner_id=existing.get("owner_id"),
                            name=existing.get("name", record["name"]),
                        )
                    records[str(slot)] = record
                    capacity.append(record)
                    available.append(record)
                    allocated += 1
                    if allocated >= needed:
                        break
                if allocated < needed:
                    raise ManagerError(
                        "Not enough positively verified empty slots. The lock may not support slot reads or capacity is occupied; no slots allocated and no PIN changes sent."
                    )
            if automatic:
                assigned = {
                    r.get("owner_id") for r in capacity if r.get("owner_id") in people
                }
                missing_users = [u for uid, u in people.items() if uid not in assigned]
                available = [
                    r
                    for r in capacity
                    if self.reusable(r) and r.get("owner_id") is None
                ]
                if len(missing_users) > len(available):
                    raise ManagerError(
                        "Not enough unassigned verified slots for all users; existing assignments preserved"
                    )
            if len(capacity) > 50:
                raise ManagerError(
                    "At most 50 HA PIN slots may be provisioned; existing records were preserved"
                )
            for person, record in zip(
                missing_users, sorted(available, key=lambda r: r["slot"])
            ):
                record.update(
                    owner_id=person.id, name=str(person.name or "HA user")[:80]
                )
            self.state["records"] = records
            await self.save(copy.deepcopy(self.state))
            return {
                "allocated": allocated,
                "total": len(capacity),
                "assigned": len(
                    {r.get("owner_id") for r in capacity if r.get("owner_id") in people}
                ),
                "discovery_complete": discovery["complete"],
                "reason": discovery.get("reason"),
            }

    async def create(self, user, pin, name=""):
        if user is None or not user.is_active or user.system_generated:
            raise ManagerError("An active personal HA account is required")
        if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{4,6}", pin):
            raise ManagerError("Enter four to six ASCII digits")
        async with self.lock:
            if any(
                pin in (r.get("pin"), r.get("pending_pin"))
                for r in self.state["records"].values()
            ):
                raise ManagerError(
                    "That PIN is already managed; choose a different PIN"
                )
            available = [
                r
                for r in self.state["records"].values()
                if self.reusable(r) and r.get("owner_id") in (None, user.id)
            ]
            if not available:
                raise ManagerError(
                    "No verified cleared slot is available. An administrator must provision more slots; unknown slots are never overwritten."
                )
            r = min(available, key=lambda r: (r.get("owner_id") != user.id, r["slot"]))
            r.update(owner_id=user.id, name=str(name or user.name or "My PIN")[:80])
            await self.save(copy.deepcopy(self.state))
            await self._mutate(user, r["slot"], "program", pin)
            return r["slot"]

    async def mutate(self, user, slot, operation, pin=None):
        async with self.lock:
            await self._mutate(user, slot, operation, pin)

    async def _mutate(self, user, slot, operation, pin=None):
        r = self.record(user, slot)
        if operation not in ("program", "delete"):
            raise ManagerError("Invalid operation")
        if (
            operation == "program"
            and r.get("source") == "august_import"
            and r.get("access_type") != "always"
        ):
            raise ManagerError(
                "This imported PIN has restricted or unknown access. Edit its schedule in the August app; local replacement would remove restrictions."
            )
        if operation == "program" and r.get("status") == "needs_attention":
            raise ManagerError(
                "Previous outcome is unknown; resolve deletion before reprogramming"
            )
        if r.get("pending_pin") and operation == "program":
            raise ManagerError(
                "Previous write outcome is unknown; resolve deletion first"
            )
        if operation == "program" and (
            not isinstance(pin, str) or not re.fullmatch(r"[0-9]{4,6}", pin)
        ):
            raise ManagerError("Enter four to six ASCII digits")
        insert = operation == "program" and self.reusable(r)
        current = r.get("pending_pin") or r.get("pin")
        if operation == "program" and not current and not insert:
            raise ManagerError(
                "This slot has not been positively verified empty; provision capacity first"
            )
        if operation == "delete" and not current:
            raise ManagerError("No current PIN is retained for deletion")
        if operation == "program":
            if any(
                other is not r and pin in (other.get("pin"), other.get("pending_pin"))
                for other in self.state["records"].values()
            ):
                raise ManagerError(
                    "That PIN is already managed; choose a different PIN"
                )
            r["pending_pin"] = pin
        r.pop("verified_empty", None)
        r["status"] = "pending"
        await self.save(copy.deepcopy(self.state))
        try:
            if operation == "delete":
                candidates = list(
                    dict.fromkeys(filter(None, [r.get("pin"), r.get("pending_pin")]))
                )
                for candidate in candidates:
                    await self.operate("delete", slot, candidate, candidate)
            else:
                await self.operate(
                    "insert" if insert else operation, slot, pin, current or pin
                )
        except InsertNotStarted:
            if not insert:
                raise
            r.pop("pending_pin", None)
            r.update(status="reserved", source="local_discovered")
            await self.save(copy.deepcopy(self.state))
            raise ManagerError(
                "Insertion blocked before any new PIN was sent: slot occupancy was not confirmed empty. Provision capacity again; do not retry deletion to fix this."
            ) from None
        except InsertRejected:
            if not insert:
                raise
            r.pop("pending_pin", None)
            # Rejection is not a fresh occupancy read. Require discovery again.
            r.update(status="reserved", source="local_discovered")
            await self.save(copy.deepcopy(self.state))
            raise ManagerError(
                "Lock rejected this new code. No working PIN was confirmed; review occupancy and keypad pairing."
            ) from None
        except Exception as exc:
            r["status"] = "needs_attention"
            await self.save(copy.deepcopy(self.state))
            # Exception from the adapter is already secret-free, but do not
            # forward arbitrary exception text from unknown libraries.
            raise ManagerError(
                "PIN outcome is unconfirmed; values retained for recovery. Do not re-add or delete blindly. Check the connection and the recorded slot state first."
            ) from None
        if operation == "program":
            r.update(
                pin=pin,
                source="local",
                status="programmed_unverified",
                access_type="always",
            )
        else:
            r.pop("pin", None)
            r.update(
                status="cleared",
                source="local",
                owner_id=None,
                name=f"Available slot {slot}",
            )
        r.pop("pending_pin", None)
        await self.save(copy.deepcopy(self.state))

    async def import_codes(self, user, codes):
        self.admin(user)
        async with self.lock:
            added = skipped = 0
            for c in codes:
                slot, pin = c.get("slot"), c.get("pin")
                if (
                    type(slot) is not int
                    or not 1 <= slot <= 255
                    or not isinstance(pin, str)
                    or not re.fullmatch(r"[0-9]{4,6}", pin)
                ):
                    skipped += 1
                    continue
                key = str(slot)
                # Never overwrite a local PIN, pending operation, or assignment.
                if key in self.state["records"] and (
                    self.state["records"][key].get("pin")
                    or self.state["records"][key].get("pending_pin")
                    or self.state["records"][key].get("owner_id")
                    or self.state["records"][key].get("source") == "local"
                ):
                    skipped += 1
                    continue
                existing = self.state["records"].get(key, {})
                self.state["records"][key] = {
                    "slot": slot,
                    "pin": pin,
                    "name": str(c.get("name") or f"Imported slot {slot}")[:80],
                    "owner_id": existing.get("owner_id"),
                    "source": "august_import",
                    "status": "imported",
                    "access_type": str(c.get("access_type", "unknown"))[:40],
                }
                added += 1
            await self.save(copy.deepcopy(self.state))
            return {"added": added, "skipped": skipped}
