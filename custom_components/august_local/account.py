"""One-time August account import. Passwords and tokens are never persisted.

This imports an already installed owner key; it is not factory commissioning.
"""
from dataclasses import dataclass, field
import re
import logging
from aiohttp import ClientError
from yalexs.exceptions import InvalidAuth

_LOGGER = logging.getLogger(__name__)
from yalexs.api_async import ApiAsync
from yalexs.authenticator_async import AuthenticatorAsync
from yalexs.authenticator_common import AuthenticationState, ValidationResult
from yalexs.const import Brand
from . import _private_protocol_logs

class AccountError(Exception):
    """Stable error code with no response bodies or credentials."""


def account_failure(exc, stage):
    """Report only fixed stage, exception type and numeric HTTP status."""
    status=getattr(exc,'status',None)
    status=status if type(status) is int else None
    _LOGGER.warning('August account request failed: stage=%s exception=%s http_status=%s',stage,type(exc).__name__,status)
    if isinstance(exc,InvalidAuth) or status in (401,403):return AccountError('invalid_auth')
    if status==429:return AccountError('rate_limited')
    if status in (400,422):return AccountError('invalid_account_request')
    if status in (404,405):return AccountError('account_endpoint_unavailable')
    if status is not None and status>=500:return AccountError('account_service_error')
    if isinstance(exc,(TimeoutError,ClientError)):return AccountError('account_connection_failed')
    if isinstance(exc,(KeyError,ValueError,TypeError,AttributeError)):return AccountError('account_response_changed')
    return AccountError('account_service_error')

@dataclass(repr=False)
class AccountLock:
    lock_id: str
    name: str
    serial: str
    address: str
    keys: list = field(repr=False)


def owner_keys(loaded):
    """Accept only installed, ordinary keys; never assume a fixed slot."""
    keys=[]
    for item in loaded or []:
        if not isinstance(item, dict):continue
        slot=item.get('slot');key=item.get('key')
        if type(slot) is int and 1 <= slot < 254 and isinstance(key,str) and re.fullmatch(r'[a-fA-F0-9]{32}',key):
            keys.append((slot,key.lower()))
    return keys

class AugustAccount:
    def __init__(self, session):
        self.api=ApiAsync(session, brand=Brand.AUGUST)
        self.auth=None
        self.token=None

    async def login(self, method, username, password):
        if method not in ('email','phone'):raise AccountError('invalid_auth')
        self.auth=AuthenticatorAsync(self.api,method,username,password)
        stage='sign_in'
        try:
            with _private_protocol_logs():
                await self.auth.async_setup_authentication()
                result=await self.auth.async_authenticate()
                self.token=result.access_token
                if result.state == AuthenticationState.REQUIRES_VALIDATION:
                    stage='send_verification'
                    await self.auth.async_send_verification_code()
                    # Keep the password only until verification completes.
                    return 'verification'
                if result.state != AuthenticationState.AUTHENTICATED:
                    self.close();raise AccountError('invalid_auth')
            self.auth._password=None
            return 'authenticated'
        except AccountError:raise
        except Exception as exc:
            self.close();raise account_failure(exc,stage) from None

    async def verify(self, code):
        if not self.auth:raise AccountError('invalid_auth')
        try:
            with _private_protocol_logs():
                result=await self.auth.async_validate_verification_code(code)
                if result != ValidationResult.VALIDATED:raise AccountError('invalid_code')
                result=await self.auth.async_authenticate()
                if result.state != AuthenticationState.AUTHENTICATED:raise AccountError('invalid_auth')
                self.token=result.access_token
            self.auth._password=None
        except AccountError:raise
        except Exception as exc:raise account_failure(exc,'verify') from None

    async def locks(self):
        if not self.token:raise AccountError('invalid_auth')
        try:
            result=[]
            with _private_protocol_logs():
                for lock in await self.api.async_get_operable_locks(self.token):
                    detail=await self.api.async_get_lock_detail(self.token,lock.device_id)
                    address=detail.mac_address
                    if not address or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address):continue
                    result.append(AccountLock(lock.device_id,lock.device_name,detail.serial_number,address.upper(),owner_keys(detail.loaded_offline_keys)))
            return result
        except AccountError:raise
        except Exception as exc:raise account_failure(exc,'list_locks') from None

    def close(self):
        if self.auth:self.auth._password=None
        self.auth=None
        self.token=None

class ConnectedAugustAccount(AugustAccount):
    """Reuse HA's official OAuth session without copying or saving its token."""
    def __init__(self, runtime):
        self.api=runtime._api
        self.gateway=runtime._gateway
        self.auth=None
        self.token=None

    async def locks(self):
        try:
            with _private_protocol_logs():
                self.token=await self.gateway.async_get_access_token()
            return await super().locks()
        except AccountError:raise
        except Exception as exc:raise account_failure(exc,'ha_account') from None
