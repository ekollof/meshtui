"""Main proxy daemon for MeshCore TCP Proxy."""

import asyncio
import logging
from typing import Optional

from .config import ProxyConfig
from .backends import Backend
from .backends.serial import SerialBackend
from .tcp_server import TCPServer

logger = logging.getLogger("meshcore.proxy")


class MeshCoreTCPProxy:
    """Main proxy daemon coordinating backend and TCP server.

    Responsibilities:
    - Initialize backend (Serial/BLE) and TCP server
    - Forward frames bidirectionally between backend and TCP clients
    - Handle connection lifecycle and errors
    """

    def __init__(self, config: ProxyConfig):
        """Initialize proxy.

        Args:
            config: Proxy configuration
        """
        self.config = config
        self.backend: Optional[Backend] = None
        self.tcp_server: Optional[TCPServer] = None
        self.running = False

        logger.info("MeshCore TCP Proxy initialized")
        logger.debug(str(config))

    async def start(self):
        """Start the proxy daemon.

        This is the main entry point that:
        1. Initializes the backend
        2. Connects to the device
        3. Starts the TCP server
        4. Runs until stopped
        """
        try:
            self.running = True

            # Initialize backend
            logger.info(f"Initializing {self.config.backend_type} backend...")
            self.backend = self._create_backend()

            # Set up frame callback: backend → TCP clients
            self.backend.set_frame_callback(self._handle_backend_frame)

            # Connect to device
            logger.info("Connecting to device...")
            connected = await self.backend.connect()

            if not connected:
                logger.error("Failed to connect to device")
                return

            logger.info("Device connected successfully")

            # Initialize TCP server
            logger.info(
                f"Starting TCP server on {self.config.listen_host}:{self.config.listen_port}..."
            )
            self.tcp_server = TCPServer(
                self.config.listen_host,
                self.config.listen_port,
                frame_callback=self._handle_tcp_frame
            )

            await self.tcp_server.start()

            logger.info("=" * 60)
            logger.info("🚀 MeshCore TCP Proxy is running!")
            logger.info(f"   Backend: {self.config.backend_type}")
            if self.config.backend_type == "serial":
                logger.info(f"   Serial: {self.config.serial_port}")
            else:
                logger.info(f"   BLE: {self.config.ble_address}")
            logger.info(f"   TCP Server: {self.config.listen_host}:{self.config.listen_port}")
            logger.info("=" * 60)

            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Proxy error: {e}", exc_info=True)
        finally:
            await self.stop()

    async def stop(self):
        """Stop the proxy daemon gracefully."""
        if not self.running:
            return

        logger.info("Shutting down proxy...")
        self.running = False

        # Stop TCP server
        if self.tcp_server:
            await self.tcp_server.stop()

        # Disconnect backend
        if self.backend:
            await self.backend.disconnect()

        logger.info("Proxy stopped")

    def _create_backend(self) -> Backend:
        """Create backend based on configuration.

        Returns:
            Backend instance

        Raises:
            ValueError: If backend type is invalid
        """
        if self.config.backend_type == "serial":
            return SerialBackend(
                self.config.serial_port,
                self.config.serial_baudrate
            )
        elif self.config.backend_type == "ble":
            # TODO: Implement BLE backend in Phase 3
            raise NotImplementedError("BLE backend not yet implemented")
        else:
            raise ValueError(f"Unknown backend type: {self.config.backend_type}")

    async def _handle_backend_frame(self, frame: bytes):
        """Handle frame received from backend device.

        Forwards frame to all connected TCP clients.

        Args:
            frame: Frame payload from device
        """
        if self.config.log_frames:
            logger.debug(f"Backend → TCP: {frame.hex()} ({len(frame)} bytes)")

        if self.tcp_server:
            await self.tcp_server.broadcast_frame(frame)

    async def _handle_tcp_frame(self, frame: bytes):
        """Handle frame received from TCP client.

        Forwards frame to backend device.

        Args:
            frame: Frame payload from TCP client
        """
        if self.config.log_frames:
            logger.debug(f"TCP → Backend: {frame.hex()} ({len(frame)} bytes)")

        if self.backend:
            await self.backend.send_frame(frame)
