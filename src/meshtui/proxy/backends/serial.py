"""Serial backend for MeshCore TCP Proxy.

Frame parsing logic copied from meshcore library (serial_cx.py).
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

import serial_asyncio

from . import Backend
from ..framing import HOST_TO_DEVICE, MAX_FRAME_SIZE, encode_frame, find_frame_start

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

        # Frame parsing state (matches current meshcore serial_cx)
        self.header = b""
        self.inframe = b""
        self.frame_expected_size = 0

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

        Device → host frames start with 0x3E; older firmware used 0x3C.
        Both markers are accepted. Leading console/debug bytes are skipped.

        Args:
            data: Raw bytes from serial port
        """
        if not data:
            return

        if len(self.header) == 0:
            idx = find_frame_start(data)
            if idx < 0:
                return
            data = data[idx:]
            self.header = data[0:1]
            data = data[1:]

        if len(self.header) < 3:
            need = 3 - len(self.header)
            self.header = self.header + data[:need]
            data = data[need:]
            if len(self.header) < 3:
                return
            self.frame_expected_size = int.from_bytes(self.header[1:3], "little")
            if self.frame_expected_size > MAX_FRAME_SIZE:
                logger.debug(
                    f"Invalid serial frame size {self.frame_expected_size}, resyncing"
                )
                leftover = data
                self.header = b""
                self.inframe = b""
                self.frame_expected_size = 0
                if leftover:
                    self.handle_rx(leftover)
                return

        remaining = self.frame_expected_size - len(self.inframe)
        if len(data) < remaining:
            self.inframe = self.inframe + data
            return

        self.inframe = self.inframe + data[:remaining]
        leftover = data[remaining:]

        if self.frame_callback is not None:
            asyncio.create_task(self.frame_callback(self.inframe))

        self.header = b""
        self.inframe = b""
        self.frame_expected_size = 0
        if leftover:
            self.handle_rx(leftover)

    async def send_frame(self, frame: bytes):
        """Send frame to serial device.

        Args:
            frame: Frame payload (without 0x3C header)
        """
        if not self.transport:
            logger.error("Transport not connected, cannot send frame")
            return

        pkt = encode_frame(frame, HOST_TO_DEVICE)

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
