"""TCP server for MeshCore TCP Proxy."""

import asyncio
import logging
from typing import Dict, Optional, Callable, Awaitable

logger = logging.getLogger("meshcore.proxy.tcp")


class TCPServer:
    """TCP server for accepting client connections.

    Handles multiple client connections and frame forwarding using the
    MeshCore framing protocol (0x3C + size + payload).
    """

    def __init__(
        self,
        host: str,
        port: int,
        frame_callback: Optional[Callable[[bytes], Awaitable[None]]] = None
    ):
        """Initialize TCP server.

        Args:
            host: Listen address (0.0.0.0 = all interfaces)
            port: Listen port
            frame_callback: Callback for frames received from clients
        """
        self.host = host
        self.port = port
        self.frame_callback = frame_callback
        self.server = None
        self.clients: Dict[asyncio.StreamReader, asyncio.StreamWriter] = {}

        logger.info(f"TCP server initialized: {host}:{port}")

    async def start(self):
        """Start TCP server and listen for connections."""
        try:
            self.server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port
            )

            addr = self.server.sockets[0].getsockname()
            logger.info(f"TCP server listening on {addr[0]}:{addr[1]}")

        except Exception as e:
            logger.error(f"Failed to start TCP server: {e}")
            raise

    async def stop(self):
        """Stop TCP server and close all connections."""
        logger.info("Stopping TCP server...")

        # Close all client connections
        for writer in list(self.clients.values()):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing client connection: {e}")

        self.clients.clear()

        # Stop server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("TCP server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle individual TCP client connection.

        Args:
            reader: Stream reader for client
            writer: Stream writer for client
        """
        addr = writer.get_extra_info('peername')
        logger.info(f"New client connected: {addr}")

        self.clients[reader] = writer

        try:
            while True:
                # Read one complete frame from client
                frame = await self._read_frame(reader)

                if not frame:
                    # Client disconnected
                    break

                logger.debug(f"Received frame from {addr}: {len(frame)} bytes")

                # Forward to backend via callback
                if self.frame_callback:
                    await self.frame_callback(frame)

        except asyncio.IncompleteReadError:
            logger.info(f"Client {addr} disconnected (incomplete read)")
        except ConnectionResetError:
            logger.info(f"Client {addr} connection reset")
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
        finally:
            # Cleanup
            if reader in self.clients:
                del self.clients[reader]

            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

            logger.info(f"Client disconnected: {addr}")

    async def _read_frame(self, reader: asyncio.StreamReader) -> Optional[bytes]:
        """Read one complete frame from TCP client.

        Frame format:
        - 0x3C (1 byte)
        - Size (2 bytes, little-endian)
        - Payload (size bytes)

        Args:
            reader: Stream reader

        Returns:
            Frame payload (without header), or None if EOF
        """
        try:
            # Read header (3 bytes)
            header = await reader.readexactly(3)

            if len(header) == 0:
                return None

            # Validate start marker
            if header[0] != 0x3C:
                logger.error(f"Invalid frame start marker: 0x{header[0]:02x}")
                return None

            # Parse size (little-endian)
            size = int.from_bytes(header[1:3], byteorder="little")

            # Read payload
            payload = await reader.readexactly(size)

            return payload

        except asyncio.IncompleteReadError:
            # Client disconnected mid-frame
            return None

    async def broadcast_frame(self, frame: bytes):
        """Send frame to all connected clients.

        Args:
            frame: Frame payload (without 0x3C header)
        """
        if not self.clients:
            logger.debug("No clients connected, frame not sent")
            return

        # Build packet with 0x3C framing
        size = len(frame)
        pkt = b"\x3c" + size.to_bytes(2, byteorder="little") + frame

        logger.debug(f"Broadcasting frame to {len(self.clients)} client(s): {len(frame)} bytes")

        # Send to all clients
        for reader, writer in list(self.clients.items()):
            try:
                writer.write(pkt)
                await writer.drain()
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                # Remove dead client
                if reader in self.clients:
                    del self.clients[reader]
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

    def set_frame_callback(self, callback: Callable[[bytes], Awaitable[None]]):
        """Set callback for frames received from clients.

        Args:
            callback: Async function called with frame payload
        """
        self.frame_callback = callback

    def get_client_count(self) -> int:
        """Get number of connected clients.

        Returns:
            Client count
        """
        return len(self.clients)
