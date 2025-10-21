"""Serial backend for MeshCore TCP Proxy.

Frame parsing logic copied from meshcore library (serial_cx.py).
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

import serial_asyncio

from . import Backend

logger = logging.getLogger("meshcore.proxy.serial")


class SerialProtocol(asyncio.Protocol):
    """Serial protocol handler."""

    def __init__(self, backend: "SerialBackend"):
        self.backend = backend

    def connection_made(self, transport):
        """Called when serial port is opened."""
        self.backend.transport = transport
        logger.debug("Serial port opened")

        # Set RTS low if possible
        if isinstance(transport, serial_asyncio.SerialTransport) and transport.serial:
            transport.serial.rts = False

        self.backend._connected_event.set()

    def data_received(self, data):
        """Called when data is received from serial port."""
        self.backend.handle_rx(data)

    def connection_lost(self, exc):
        """Called when serial port is closed."""
        logger.debug("Serial port closed")
        self.backend._connected_event.clear()

        if exc:
            logger.error(f"Serial connection lost with error: {exc}")


class SerialBackend(Backend):
    """Serial port backend using pyserial.

    Implements the MeshCore framing protocol:
    - Start byte: 0x3C
    - Size: 2 bytes, little-endian
    - Payload: Variable length
    """

    def __init__(self, port: str, baudrate: int = 115200):
        """Initialize serial backend.

        Args:
            port: Serial port path (e.g., /dev/ttyUSB0)
            baudrate: Connection baudrate (default: 115200)
        """
        self.port = port
        self.baudrate = baudrate
        self.transport = None
        self.frame_callback: Optional[Callable[[bytes], Awaitable[None]]] = None

        # Frame parsing state (copied from meshcore)
        self.frame_started = False
        self.frame_size = 0
        self.header = b""
        self.inframe = b""

        # Connection state
        self._connected_event = asyncio.Event()

        logger.info(f"Serial backend initialized: {port} @ {baudrate} baud")

    async def connect(self) -> bool:
        """Open serial port.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._connected_event.clear()

            logger.info(f"Connecting to serial port: {self.port}")

            loop = asyncio.get_running_loop()
            await serial_asyncio.create_serial_connection(
                loop,
                lambda: SerialProtocol(self),
                self.port,
                baudrate=self.baudrate,
            )

            # Wait for connection_made callback
            await asyncio.wait_for(self._connected_event.wait(), timeout=5.0)

            logger.info(f"Serial connection established: {self.port}")
            return True

        except asyncio.TimeoutError:
            logger.error(f"Timeout connecting to {self.port}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            return False

    async def disconnect(self):
        """Close serial port."""
        if self.transport:
            self.transport.close()
            self.transport = None
            self._connected_event.clear()
            logger.info("Serial connection closed")

    def handle_rx(self, data: bytes):
        """Parse incoming serial data into frames.

        This is copied directly from meshcore's serial_cx.py handle_rx() method.
        It handles the 0x3C framing protocol with proper state management.

        Args:
            data: Raw bytes from serial port
        """
        headerlen = len(self.header)
        framelen = len(self.inframe)

        if not self.frame_started:  # Wait for start of frame
            if len(data) >= 3 - headerlen:
                self.header = self.header + data[: 3 - headerlen]
                self.frame_started = True
                self.frame_size = int.from_bytes(self.header[1:], byteorder="little")
                self.handle_rx(data[3 - headerlen :])
            else:
                self.header = self.header + data
        else:
            if framelen + len(data) < self.frame_size:
                self.inframe = self.inframe + data
            else:
                self.inframe = self.inframe + data[: self.frame_size - framelen]

                # Complete frame received - call callback
                if self.frame_callback is not None:
                    asyncio.create_task(self.frame_callback(self.inframe))

                # Reset for next frame
                self.frame_started = False
                self.header = b""
                self.inframe = b""

                # Handle any remaining data
                if framelen + len(data) > self.frame_size:
                    self.handle_rx(data[self.frame_size - framelen :])

    async def send_frame(self, frame: bytes):
        """Send frame to serial device.

        Args:
            frame: Frame payload (without 0x3C header)
        """
        if not self.transport:
            logger.error("Transport not connected, cannot send frame")
            return

        # Build packet with 0x3C framing
        size = len(frame)
        pkt = b"\x3c" + size.to_bytes(2, byteorder="little") + frame

        logger.debug(f"Sending frame: {pkt.hex()} ({len(frame)} bytes payload)")
        self.transport.write(pkt)

    def set_frame_callback(self, callback: Callable[[bytes], Awaitable[None]]):
        """Set callback for received frames.

        Args:
            callback: Async function called with frame payload
        """
        self.frame_callback = callback

    def is_connected(self) -> bool:
        """Check if serial port is connected.

        Returns:
            True if connected, False otherwise
        """
        return self.transport is not None and self._connected_event.is_set()
