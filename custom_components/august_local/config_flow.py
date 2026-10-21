"""UI setup, including one-time import of an installed August owner key."""
import asyncio
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from yalexs_ble import PushLock, AuthError
from . import DOMAIN, _private_protocol_logs
from .account import AugustAccount, ConnectedAugustAccount, AccountError
from .enrollment import ASL05Enrollment, EnrollmentError


class AccountSteps:
    _account = None
    _account_session = None
    _account_locks = None
    _selected_lock = None

    async def _forget_account(self):
        if self._account:self._account.close()
        self._account = None
        if self._account_session is not None:
            await self._account_session.close()
            self._account_session = None
        self._account_locks = None
        self._selected_lock = None

    async def async_step_ha_account(self,user_input=None):
        entries=[e for e in self.hass.config_entries.async_entries('august') if getattr(e,'runtime_data',None) is not None]
        if not entries:return self.async_abort(reason='no_loaded_august_account')
        errors={}
        if user_input is not None:
            entry=next((e for e in entries if e.entry_id==user_input['cloud_entry_id']),None)
            if entry is None:errors['base']='invalid_selection'
            else:
                await self._forget_account()
                self._account=ConnectedAugustAccount(entry.runtime_data)
                return await self.async_step_account_lock()
        choices=[selector.SelectOptionDict(value=e.entry_id,label=e.title) for e in entries]
        return self.async_show_form(step_id='ha_account',errors=errors,data_schema=vol.Schema({vol.Required('cloud_entry_id',default=entries[0].entry_id if len(entries)==1 else vol.UNDEFINED):selector.SelectSelector(selector.SelectSelectorConfig(options=choices))}))

    async def async_step_account(self, user_input=None):
        errors={}
        if user_input is not None:
            await self._forget_account()
            # Match HA's official August integration: shared HTTP sessions can
            # carry another service's cookies and trigger August's WAF.
            self._account_session=async_create_clientsession(self.hass)
            self._account=AugustAccount(self._account_session)
            try:
                state=await self._account.login(user_input['login_method'],user_input['username'].strip(),user_input['password'])
                if state=='verification':return await self.async_step_verification()
                return await self.async_step_account_lock()
            except AccountError as exc:errors['base']=str(exc)
        return self.async_show_form(step_id='account',errors=errors,data_schema=vol.Schema({
            vol.Required('login_method',default='email'):selector.SelectSelector(selector.SelectSelectorConfig(options=['email','phone'])),
            vol.Required('username'):str,
            vol.Required('password'):selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }))

    async def async_step_verification(self,user_input=None):
        errors={}
        if self._account is None:return await self.async_step_account()
        if user_input is not None:
            try:
                await self._account.verify(user_input['code'].strip())
                return await self.async_step_account_lock()
            except AccountError as exc:errors['base']=str(exc)
        return self.async_show_form(step_id='verification',errors=errors,data_schema=vol.Schema({vol.Required('code'):str}))

    async def async_step_account_lock(self,user_input=None):
        errors={}
        if self._account is None:return await self.async_step_account()
        if self._account_locks is None:
            try:self._account_locks=await self._account.locks()
            except AccountError as exc:
                await self._forget_account()
                return self.async_abort(reason=str(exc))
        if not self._account_locks:
            await self._forget_account();return self.async_abort(reason='no_account_locks')
        if user_input is not None:
            lock=next((x for x in self._account_locks if x.lock_id==user_input['lock_id']),None)
            if lock is None:errors['base']='invalid_selection'
            elif not lock.keys:errors['base']='no_offline_key'
            else:
                self._selected_lock=lock
                return await self.async_step_connect()
        choices=[selector.SelectOptionDict(value=x.lock_id,label=x.name) for x in self._account_locks]
        return self.async_show_form(step_id='account_lock',errors=errors,data_schema=vol.Schema({vol.Required('lock_id'):selector.SelectSelector(selector.SelectSelectorConfig(options=choices))}))

    async def async_step_connect(self,user_input=None):
        errors={};lock=self._selected_lock
        if lock is None:return await self.async_step_account()
        if user_input is not None:
            device=bluetooth.async_ble_device_from_address(self.hass,lock.address,True)
            if device is None:errors['base']='bluetooth_connection_failed'
            else:
                found=None
                try:
                    with _private_protocol_logs():
                        for slot,key in lock.keys:
                            try:
                                await asyncio.wait_for(PushLock(lock.serial,device.address,device,key,slot).validate(),45)
                                found=(slot,key);break
                            except AuthError:continue
                except Exception:errors['base']='bluetooth_connection_failed'
                if found is None and not errors:errors['base']='bluetooth_auth_failed'
                if found:
                    data={'name':lock.name,'address':lock.address,'serial':lock.serial,'key':found[1],'slot':found[0]}
                    try:return await self._finish_account_lock(data)
                    finally:await self._forget_account()
        return self.async_show_form(step_id='connect',errors=errors,data_schema=vol.Schema({}),description_placeholders={'name':lock.name})

    async def _finish_account_lock(self,data):
        if isinstance(self,config_entries.OptionsFlow):
            current=self.hass.config_entries.async_get_entry(self.config_entry.data['entry_id'])
            if current is None or current.data.get('address','').upper()!=data['address']:
                return self.async_abort(reason='different_lock')
        # Use the upstream discovery flow so HA performs its usual identity,
        # credential update, and read-only validation checks.
        result=await self.hass.config_entries.flow.async_init('yalexs_ble',context={'source':'integration_discovery'},data=data)
        if result['type']=='form':
            if result.get('step_id')!='integration_discovery_confirm':
                return self.async_abort(reason='bluetooth_setup_failed')
            result=await self.hass.config_entries.flow.async_configure(result['flow_id'],{})
        if result['type']=='create_entry':ble=result['result']
        elif result['type']=='abort' and result.get('reason')=='already_configured':
            ble=next((e for e in self.hass.config_entries.async_entries('yalexs_ble') if e.data.get('address','').upper()==data['address']),None)
            if ble is None:return self.async_abort(reason='bluetooth_setup_failed')
        else:return self.async_abort(reason='bluetooth_setup_failed')
        settings={'entry_id':ble.entry_id,'owned_slots':[],'ui_pins':True}
        if isinstance(self,config_entries.OptionsFlow):
            if self.config_entry.data['entry_id']!=ble.entry_id:
                return self.async_abort(reason='different_lock')
            return self.async_create_entry(title='',data=dict(self.config_entry.options))
        return self.async_create_entry(title='August Local',data=settings)


class ConfigFlow(AccountSteps,config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=1

    async def async_step_user(self,user_input=None):
        if self._async_current_entries():return self.async_abort(reason='single_instance_allowed')
        return self.async_show_menu(step_id='user',menu_options={'enroll':'Set up lock locally (experimental)','existing':'Use an existing HA Bluetooth lock','ha_account':'Use August account connected to HA','account':'Legacy August sign-in (optional)'})
    
    async def async_step_enroll(self,user_input=None):
        errors={}
        if user_input is not None:
            lock_mac=user_input['lock_mac'].upper().strip()
            if not self._is_valid_mac(lock_mac):errors['base']='invalid_mac'
            else:
                device=bluetooth.async_ble_device_from_address(self.hass,lock_mac,connectable=True)
                if device is None:errors['base']='no_connectable_device'
                else:
                    try:
                        enrollment=ASL05Enrollment(lock_mac,device=device)
                        key=await enrollment.enroll()
                        data={'address':lock_mac,'key':key.hex()}
                        return await self._finish_account_lock(data)
                    except EnrollmentError:errors['base']='enrollment_failed'
        return self.async_show_form(step_id='enroll',errors=errors,data_schema=vol.Schema({vol.Required('lock_mac'):selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT))}))
    
    @staticmethod
    def _is_valid_mac(mac:str)->bool:
        parts=mac.split(':')
        return len(parts)==6 and all(len(p)==2 and all(c in '0123456789ABCDEF' for c in p) for p in parts)

    async def async_step_existing(self,user_input=None):
        entries=self.hass.config_entries.async_entries('yalexs_ble')
        if not entries:return self.async_abort(reason='no_lock')
        if user_input is not None:
            entry=next((e for e in entries if e.entry_id==user_input['entry_id']),None)
            if entry is None:return self.async_abort(reason='invalid_selection')
            return self.async_create_entry(title='August Local',data={'entry_id':entry.entry_id,'owned_slots':[],'ui_pins':True})
        choices=[selector.SelectOptionDict(value=e.entry_id,label=e.title) for e in entries]
        return self.async_show_form(step_id='existing',data_schema=vol.Schema({vol.Required('entry_id'):selector.SelectSelector(selector.SelectSelectorConfig(options=choices))}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):return OptionsFlow()


class OptionsFlow(AccountSteps,config_entries.OptionsFlow):
    async def async_step_init(self,user_input=None):
        return self.async_show_menu(step_id='init',menu_options={'manage':'Open PIN management','ha_account':'Use August account connected to HA','account':'Legacy August sign-in (optional)'})

    async def async_step_manage(self,user_input=None):
        if user_input is not None:return self.async_create_entry(title='',data=dict(self.config_entry.options))
        return self.async_show_form(step_id='manage',data_schema=vol.Schema({}))
