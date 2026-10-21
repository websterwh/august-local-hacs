"""PIN registry and per-user access policy; never log record contents."""
import asyncio
import copy
import re

class ManagerError(Exception):
    pass

class InsertRejected(ManagerError):
    """Lock definitively rejected insertion; no new credential committed."""

class PinManager:
    def __init__(self, state, save, operate):
        self.state = state
        self.save = save
        self.operate = operate
        self.lock = asyncio.Lock()

    @staticmethod
    def admin(user):
        if user is None or not user.is_active or not user.is_admin:
            raise ManagerError('Administrator access required')

    @staticmethod
    def visible(user, record):
        return user is not None and user.is_active and (user.is_admin or record.get('owner_id') == user.id)

    def record(self, user, slot):
        r = self.state['records'].get(str(slot))
        if r is None or not self.visible(user, r):
            raise ManagerError('This slot is not assigned to you')
        return r

    def listing(self, user):
        return [{k: r.get(k) for k in ('slot', 'name', 'owner_id', 'source', 'status', 'access_type')}
                | {'has_pin': bool(r.get('pin') or r.get('pending_pin'))}
                for r in self.state['records'].values() if self.visible(user, r)]

    async def assign(self, user, slot, owner_id, name):
        self.admin(user)
        async with self.lock:
            r = self.record(user, slot)
            if r.get('pending_pin'):
                raise ManagerError('Resolve the pending operation before changing ownership')
            r.update(owner_id=owner_id, name=name[:80])
            await self.save(copy.deepcopy(self.state))

    async def reserve(self, user, first, last, confirmed_unused):
        self.admin(user)
        if confirmed_unused is not True:
            raise ManagerError('Confirm this range is unused and dedicated to HA')
        if type(first) is not int or type(last) is not int or not 1 <= first <= last <= 255:
            raise ManagerError('Choose a slot range between 1 and 255')
        if last - first >= 50:
            raise ManagerError('Reserve at most 50 slots at a time')
        async with self.lock:
            if any(str(slot) in self.state['records'] for slot in range(first, last + 1)):
                raise ManagerError('Range overlaps an existing managed slot; choose an unused range')
            for slot in range(first, last + 1):
                self.state['records'][str(slot)] = {
                    'slot':slot, 'name':f'Available slot {slot}', 'owner_id':None,
                    'source':'local_reserved', 'status':'reserved', 'access_type':'always'}
            await self.save(copy.deepcopy(self.state))
        return last - first + 1

    async def create(self, user, pin, name=''):
        if user is None or not user.is_active or user.system_generated:
            raise ManagerError('An active personal HA account is required')
        if not isinstance(pin, str) or not re.fullmatch(r'[0-9]{4,6}', pin):
            raise ManagerError('Enter four to six ASCII digits')
        async with self.lock:
            if any(pin in (r.get('pin'), r.get('pending_pin')) for r in self.state['records'].values()):
                raise ManagerError('That PIN is already managed; choose a different PIN')
            available = [r for r in self.state['records'].values()
                         if r.get('status') in ('cleared', 'reserved') and not r.get('pin') and not r.get('pending_pin')
                         and r.get('owner_id') in (None, user.id)]
            if not available:
                raise ManagerError('No verified cleared slot is available. An administrator must provision more slots; unknown slots are never overwritten.')
            r = min(available, key=lambda r:r['slot'])
            r.update(owner_id=user.id, name=str(name or user.name or 'My PIN')[:80])
            await self.save(copy.deepcopy(self.state))
            await self._mutate(user, r['slot'], 'program', pin)
            return r['slot']

    async def mutate(self, user, slot, operation, pin=None):
        async with self.lock:
            await self._mutate(user, slot, operation, pin)

    async def _mutate(self, user, slot, operation, pin=None):
        r = self.record(user, slot)
        if operation not in ('program', 'delete'):
            raise ManagerError('Invalid operation')
        if r.get('pending_pin') and operation == 'program':
            raise ManagerError('Previous write outcome is unknown; resolve deletion first')
        if operation == 'program' and (not isinstance(pin, str) or not re.fullmatch(r'[0-9]{4,6}', pin)):
            raise ManagerError('Enter four to six ASCII digits')
        insert = operation == 'program' and r.get('status') == 'reserved' and not r.get('pin')
        current = r.get('pending_pin') or r.get('pin')
        if operation == 'delete' and not current:
            raise ManagerError('No current PIN is retained for deletion')
        if operation == 'program':
            if any(other is not r and pin in (other.get('pin'), other.get('pending_pin')) for other in self.state['records'].values()):
                raise ManagerError('That PIN is already managed; choose a different PIN')
            r['pending_pin'] = pin
        r['status'] = 'pending'
        await self.save(copy.deepcopy(self.state))
        try:
            if operation == 'delete':
                candidates = list(dict.fromkeys(filter(None, [r.get('pin'), r.get('pending_pin')])))
                for candidate in candidates:
                    await self.operate('delete', slot, candidate, candidate)
            else:
                await self.operate('insert' if insert else operation, slot, pin, current or pin)
        except InsertRejected:
            if not insert:
                raise
            r.pop('pending_pin', None)
            r.update(status='reserved', source='local_reserved')
            await self.save(copy.deepcopy(self.state))
            raise ManagerError('Lock rejected this new code; choose another PIN or check capacity. Slot reservation retained.') from None
        except Exception as exc:
            r['status'] = 'needs_attention'
            await self.save(copy.deepcopy(self.state))
            # Exception from the adapter is already secret-free, but do not
            # forward arbitrary exception text from unknown libraries.
            raise ManagerError('Bluetooth operation failed; values retained. Check the local connection and retry deletion.') from None
        if operation == 'program':
            r.update(pin=pin, source='local', status='active', access_type='always')
        else:
            r.pop('pin', None)
            r.update(status='cleared', source='local', owner_id=None, name=f'Available slot {slot}')
        r.pop('pending_pin', None)
        await self.save(copy.deepcopy(self.state))


    async def import_codes(self, user, codes):
        self.admin(user)
        async with self.lock:
            added = skipped = 0
            for c in codes:
                slot, pin = c.get('slot'), c.get('pin')
                if type(slot) is not int or not 1 <= slot <= 255 or not isinstance(pin, str) or not re.fullmatch(r'[0-9]{4,6}', pin):
                    skipped += 1; continue
                key = str(slot)
                # Never overwrite a local PIN, pending operation, or assignment.
                if key in self.state['records'] and (self.state['records'][key].get('pin') or self.state['records'][key].get('pending_pin') or self.state['records'][key].get('source') == 'local'):
                    skipped += 1; continue
                existing = self.state['records'].get(key, {})
                self.state['records'][key] = {'slot': slot, 'pin': pin, 'name': str(c.get('name') or f'Imported slot {slot}')[:80],
                    'owner_id': existing.get('owner_id'), 'source': 'august_import', 'status': 'imported',
                    'access_type': str(c.get('access_type', 'unknown'))[:40]}
                added += 1
            await self.save(copy.deepcopy(self.state))
            return {'added': added, 'skipped': skipped}
