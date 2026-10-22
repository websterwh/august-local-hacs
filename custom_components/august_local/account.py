"""One-time August account import. Passwords and tokens are never persisted.

This imports an already installed owner key; it is not factory commissioning.
"""

import logging
import re
from dataclasses import dataclass, field

from aiohttp import ClientError
from yalexs.exceptions import AugustApiAIOHTTPError, InvalidAuth

from . import _private_protocol_logs

_LOGGER = logging.getLogger(__name__)


class AccountError(Exception):
    """Stable error code with no response bodies or credentials."""


def account_failure(exc):
    """Map account failures to fixed codes without response bodies or credentials."""
    status = getattr(exc, "status", None)
    status = status if type(status) is int else None
    if isinstance(exc, InvalidAuth) or status in (401, 403):
        return AccountError("invalid_auth")
    if status == 429:
        return AccountError("rate_limited")
    if status in (400, 422):
        return AccountError("invalid_account_request")
    if status in (404, 405):
        return AccountError("account_endpoint_unavailable")
    if status is not None and status >= 500:
        return AccountError("account_service_error")
    if isinstance(exc, (TimeoutError, ClientError)):
        return AccountError("account_connection_failed")
    if isinstance(exc, (KeyError, ValueError, TypeError, AttributeError)):
        return AccountError("account_response_changed")
    return AccountError("account_service_error")


@dataclass(repr=False)
class AccountLock:
    lock_id: str
    name: str
    serial: str
    address: str
    keys: list = field(repr=False)


def owner_keys(loaded):
    """Accept only installed, ordinary keys; never assume a fixed slot."""
    keys = []
    for item in loaded or []:
        if not isinstance(item, dict):
            continue
        slot = item.get("slot")
        key = item.get("key")
        if (
            type(slot) is int
            and 1 <= slot < 254
            and isinstance(key, str)
            and re.fullmatch(r"[a-fA-F0-9]{32}", key)
        ):
            keys.append((slot, key.lower()))
    return keys


class ConnectedAugustAccount:
    """Reuse HA's official OAuth session without copying or saving its token."""

    def __init__(self, runtime):
        try:
            self.api = runtime._api
            self.gateway = runtime._gateway
        except AttributeError:
            raise AccountError("account_response_changed") from None

    async def locks(self):
        try:
            result = []
            with _private_protocol_logs():
                token = await self.gateway.async_get_access_token()
                for lock in await self.api.async_get_operable_locks(token):
                    detail = await self.api.async_get_lock_detail(token, lock.device_id)
                    address = detail.mac_address
                    if not address or not re.fullmatch(
                        r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", address
                    ):
                        continue
                    result.append(
                        AccountLock(
                            lock.device_id,
                            lock.device_name,
                            detail.serial_number,
                            address.upper(),
                            owner_keys(detail.loaded_offline_keys),
                        )
                    )
            return result
        except AccountError:
            raise
        except (
            AugustApiAIOHTTPError,
            ClientError,
            TimeoutError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            status = getattr(exc, "status", None)
            _LOGGER.warning(
                "August account request failed: stage=ha_account exception=%s http_status=%s",
                type(exc).__name__,
                status if type(status) is int else None,
            )
            raise account_failure(exc) from None

    def close(self):
        """Discard borrowed references; never closes the official session."""
        self.api = None
        self.gateway = None
