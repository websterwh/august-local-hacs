"""Experimental server-assisted handshake, separate from the local PIN path.

Not exposed as factory setup: registration, key installation, calibration and
recovery must be implemented and verified before it can commission a lock.
"""
import asyncio
from dataclasses import dataclass, field
import os
import re
import struct
from aiohttp import ClientTimeout
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from yalexs.api_common import _api_headers
from yalexs.const import Brand
from yalexs_ble import util
from . import _private_protocol_logs

class CommissioningError(Exception):
    """Nonsecret failure; callers must not retry a timed-out write blindly."""

class AugustSetupAPI:
    """Exact SDK handshake routes. No automatic retries or response logging."""
    def __init__(self, account):
        self.account=account

    async def _put(self,path,payload,params=None):
        if not self.account.token:raise CommissioningError('Account authentication required')
        try:
            with _private_protocol_logs():
                response=await self.account.api._aiohttp_session.request(
                    'PUT',self.account.api.get_brand_url(path),
                    json=payload,params=params,headers=_api_headers(self.account.token,Brand.AUGUST),
                    timeout=ClientTimeout(total=20),allow_redirects=False)
                try:
                    if response.status!=200:raise CommissioningError(f'August setup request rejected (HTTP {response.status})')
                    data=await response.json()
                    if not isinstance(data,dict):raise CommissioningError('Unexpected setup response')
                    return data
                finally:response.release()
        except CommissioningError:raise
        except Exception:raise CommissioningError('August setup request failed; outcome unknown') from None

    @staticmethod
    def _lock_id(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,128}',value):raise CommissioningError('Invalid lock identifier')
        return value

    async def begin(self,lock_id,mrand1,mrand2):
        for value in (mrand1,mrand2):
            if type(value) is not int or not -(2**31)<=value<2**31:raise CommissioningError('Invalid client random value')
        data=await self._put('/locks/initiatecomm/'+self._lock_id(lock_id),{'mRand1':str(mrand1),'mRand2':str(mrand2)})
        try:
            value=data['packet']
            if not isinstance(value,str) or not re.fullmatch(r'[0-9A-Fa-f]{36}',value):raise ValueError
            frame=bytes.fromhex(value)
            if frame[16]!=15:raise ValueError
            return frame
        except (KeyError,ValueError):raise CommissioningError('Invalid server handshake packet') from None

    async def finalize(self,lock_id,reply):
        if not isinstance(reply,bytes) or len(reply)!=18 or reply[16]!=15:raise CommissioningError('Invalid lock handshake reply')
        data=await self._put('/locks/getlockrands/'+self._lock_id(lock_id),{'LockResponse':reply.hex()})
        try:
            values=[data[x] for x in ('lRand1','lRand2','slot')]
            if any(type(x) is not int for x in values):raise ValueError
            if not all(-(2**31)<=x<2**32 for x in values[:2]) or not 0<=values[2]<=255:raise ValueError
            return values
        except (KeyError,ValueError):raise CommissioningError('Invalid server random response') from None

@dataclass(repr=False)
class OnlineSecuritySession:
    """Independent continuous security CBC contexts, as in the Android SDK."""
    slot: int
    key: bytes = field(repr=False)
    _encrypt: object = field(init=False,repr=False)
    _decrypt: object = field(init=False,repr=False)

    def __post_init__(self):
        if len(self.key)!=16 or type(self.slot) is not int or not 0<=self.slot<=255:raise CommissioningError('Invalid security session')
        self._encrypt=Cipher(algorithms.AES(self.key),modes.CBC(bytes(16))).encryptor()
        self._decrypt=Cipher(algorithms.AES(self.key),modes.CBC(bytes(16))).decryptor()

    def encode(self,opcode,payload=b''):
        if not 0<=opcode<=255 or len(payload)>8:raise CommissioningError('Invalid security command')
        frame=bytearray(18);frame[0]=opcode;frame[4:4+len(payload)]=payload;frame[16:]=bytes([15,self.slot])
        frame[12:16]=util._security_checksum(frame).to_bytes(4,'little')
        return self._encrypt.update(bytes(frame[:16]))+bytes(frame[16:])

    def decode(self,frame,expected_opcode):
        if len(frame)!=18 or frame[16:]!=bytes([15,self.slot]):raise CommissioningError('Invalid security response')
        plain=self._decrypt.update(frame[:16])+frame[16:]
        if plain[0]!=expected_opcode or util._security_checksum(plain)!=int.from_bytes(plain[12:16],'little'):raise CommissioningError('Security response validation failed')
        return plain

async def authenticate_online(api,lock_id,exchange,*,random_bytes=os.urandom):
    """Authenticate only. exchange sends one security packet and awaits its reply.

    No reset, enrollment write, motor operation or PIN command occurs here.
    The caller must own the connection, subscribe first and close on any error.
    """
    client_random=random_bytes(8)
    if len(client_random)!=8:raise CommissioningError('Invalid random source')
    m1,m2=struct.unpack('<ii',client_random)
    challenge=await api.begin(lock_id,m1,m2)
    reply=await asyncio.wait_for(exchange(challenge),15)
    if not isinstance(reply,bytes) or len(reply)!=18 or reply[16:]!=challenge[16:]:raise CommissioningError('Unexpected lock handshake reply')
    l1,l2,slot=await api.finalize(lock_id,reply)
    if slot!=challenge[17]:raise CommissioningError('Server and lock slots do not match')
    session=OnlineSecuritySession(slot,client_random+struct.pack('<II',l1&0xffffffff,l2&0xffffffff))
    initialization=random_bytes(8)
    if len(initialization)!=8:raise CommissioningError('Invalid random source')
    response=await asyncio.wait_for(exchange(session.encode(3,initialization)),15)
    plain=session.decode(response,4)
    if plain[4:12]!=initialization:raise CommissioningError('Initialization random values do not match')
    # The Android SDK resets all four CBC contexts after initialization.
    return OnlineSecuritySession(slot,session.key)
