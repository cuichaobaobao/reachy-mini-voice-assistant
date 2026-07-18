"""Runs mDNS zeroconf service discovery for Home Assistant."""

import logging
import socket

from ..core.util import get_mac

_LOGGER = logging.getLogger(__name__)

try:
    from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

    ZEROCONF_AVAILABLE = True
except ImportError:
    _LOGGER.fatal("pip install zeroconf")
    raise

MDNS_TARGET_IP = "224.0.0.251"


def get_default_device_name(prefix: str = "reachy-mini-voice") -> str:
    """Build a stable zero-config device name from the MAC address."""
    mac = get_mac().replace(":", "").lower()
    suffix = mac[-6:] if len(mac) >= 6 else mac or "device"
    return f"{prefix}-{suffix}" if prefix else suffix


def get_default_friendly_name() -> str:
    """Build a stable friendly name for Home Assistant discovery."""
    return f"Reachy Mini Voice Assistant {get_default_device_name(prefix='')[-6:].upper()}"


def get_local_ip() -> str:
    """Get local IP address for mDNS."""
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    test_sock.setblocking(False)
    try:
        test_sock.connect((MDNS_TARGET_IP, 1))
        return test_sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        test_sock.close()


class HomeAssistantZeroconf:
    """Zeroconf service for Home Assistant discovery."""

    def __init__(self, port: int, name: str | None = None, host: str | None = None) -> None:
        self.port = port
        self.name = name or get_default_device_name()

        if not host:
            host = get_local_ip()
            _LOGGER.debug("Detected IP: %s", host)

        assert host
        self.host = host
        self._aiozc = AsyncZeroconf()

    async def register_server(self) -> None:
        mac_address = get_mac()
        service_info = AsyncServiceInfo(
            "_esphomelib._tcp.local.",
            f"{self.name}._esphomelib._tcp.local.",
            addresses=[socket.inet_aton(self.host)],
            port=self.port,
            properties={
                "version": "2025.9.0",
                "mac": mac_address,
                "board": "reachy_mini",
                "platform": "REACHY_MINI",
                "network": "ethernet",
            },
            server=f"{self.name}.local.",
        )

        await self._aiozc.async_register_service(service_info)
        _LOGGER.debug("Zeroconf discovery enabled: %s", service_info)

    async def unregister_server(self) -> None:
        await self._aiozc.async_close()
