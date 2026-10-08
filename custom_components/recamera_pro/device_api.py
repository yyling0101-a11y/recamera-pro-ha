"""Authenticated client for a reCamera Pro device."""

from __future__ import annotations

import base64
from dataclasses import dataclass

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding


class RecameraAuthenticationError(Exception):
    """Raised when device credentials are rejected."""


@dataclass(slots=True)
class RecameraDeviceInfo:
    """Safe device metadata returned by the local device API."""

    base_plate_model: str | None = None
    firmware_version: str | None = None
    sensor_model: str | None = None
    serial_number: str | None = None


class RecameraDeviceClient:
    """Small client for login, metadata and authenticated device URLs."""

    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host.strip()
        self.username = username.strip() or "admin"
        self.password = password
        self._session: aiohttp.ClientSession | None = None

    async def async_connect(self) -> RecameraDeviceInfo:
        """Log in using the device public key and return safe metadata."""
        connector = aiohttp.TCPConnector(ssl=False)
        self._session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        api_base = f"https://{self.host}/cgi-bin/entry.cgi"
        try:
            async with self._session.get(
                f"{api_base}/system/key", timeout=aiohttp.ClientTimeout(total=8)
            ) as response:
                response.raise_for_status()
                public_key_pem = (await response.json())["sPublicKey"].encode()

            public_key = serialization.load_pem_public_key(public_key_pem)
            encrypted_password = base64.b64encode(
                public_key.encrypt(self.password.encode(), padding.PKCS1v15())
            ).decode()
            async with self._session.post(
                f"{api_base}/system/login",
                json={
                    "sUserName": self.username,
                    "sPassword": encrypted_password,
                },
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                response.raise_for_status()
                login_data = await response.json()
                if login_data.get("iStatus") != 0 or login_data.get("iAuth") != 1:
                    raise RecameraAuthenticationError("invalid_auth")

            async with self._session.get(
                f"{api_base}/system/device-info",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                response.raise_for_status()
                data = await response.json()
            return RecameraDeviceInfo(
                base_plate_model=data.get("sBasePlateModel"),
                firmware_version=data.get("sFirmwareVersion"),
                sensor_model=data.get("sSensorModel"),
                serial_number=data.get("sSerialNumber"),
            )
        except Exception:
            await self.async_close()
            raise

    async def async_close(self) -> None:
        """Close the dedicated authenticated session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def async_open_websocket(
        self, path: str, *, protocols: tuple[str, ...] = ()
    ) -> aiohttp.ClientWebSocketResponse:
        """Open an authenticated device WebSocket using the login session."""
        if self._session is None or self._session.closed:
            await self.async_connect()
        return await self._session.ws_connect(
            f"wss://{self.host}{path}",
            protocols=protocols,
            heartbeat=30,
        )


async def async_validate_device(
    host: str, username: str, password: str
) -> RecameraDeviceInfo:
    """Validate credentials without retaining a device session."""
    client = RecameraDeviceClient(host, username, password)
    try:
        return await client.async_connect()
    finally:
        await client.async_close()
