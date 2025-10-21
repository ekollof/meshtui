"""Backend interfaces for MeshCore TCP Proxy."""

from abc import ABC, abstractmethod
from typing import Callable, Awaitable


class Backend(ABC):
    """Abstract backend interface for MeshCore device connections."""

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to device.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """Disconnect from device."""
        pass

    @abstractmethod
    async def send_frame(self, frame: bytes):
        """Send frame to device.

        Args:
            frame: Frame payload (without 0x3C header)
        """
        pass

    @abstractmethod
    def set_frame_callback(self, callback: Callable[[bytes], Awaitable[None]]):
        """Set callback for received frames.

        Args:
            callback: Async function called with frame payload
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status.

        Returns:
            True if connected, False otherwise
        """
        pass
