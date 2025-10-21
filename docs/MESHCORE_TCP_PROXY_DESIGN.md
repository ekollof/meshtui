# MeshCore TCP Proxy - Design Document

**Version**: 1.0
**Date**: 2025-10-21
**Author**: Design by Claude Code
**Status**: Design Phase

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Solution Architecture](#solution-architecture)
4. [Protocol Analysis](#protocol-analysis)
5. [Component Design](#component-design)
6. [Implementation Plan](#implementation-plan)
7. [Configuration](#configuration)
8. [Testing Strategy](#testing-strategy)
9. [Future Enhancements](#future-enhancements)
10. [References](#references)

---

## Overview

**MeshCore TCP Proxy** is a daemon service that exposes USB Serial or BLE-connected MeshCore devices over TCP/IP, making them accessible to MeshTUI's TCP connection mode without requiring WiFi-enabled firmware on the device.

### Purpose
- Enable TCP connectivity testing without WiFi firmware
- Allow remote network access to locally-connected devices
- Support multiple simultaneous client connections to one device
- Provide location independence for MeshCore devices

### Key Features
- Zero protocol translation (same framing across all transports)
- Support for Serial and BLE backends
- Multi-client TCP server
- Daemon mode with systemd integration
- YAML-based configuration
- Comprehensive logging

---

## Problem Statement

### Current Situation
- MeshTUI supports three connection types: Serial, BLE, and TCP
- TCP mode requires MeshCore devices with WiFi firmware
- No way to test TCP connectivity without WiFi hardware
- Cannot access USB/BLE devices remotely over network

### Requirements
1. Expose Serial/BLE devices as TCP endpoints
2. Maintain protocol compatibility with MeshTUI
3. Support multiple simultaneous TCP clients
4. Run as system daemon (background service)
5. Minimal latency overhead
6. Robust error handling and reconnection

### Non-Goals
- Protocol translation (not needed - already identical)
- Device discovery/scanning (manual configuration)
- Built-in authentication (use firewall/VPN for security)
- Cross-platform GUI (CLI/config file only)

---

## Solution Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MeshCore TCP Proxy Daemon                   │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    TCP Server Layer                       │ │
│  │  - Listen on 0.0.0.0:5000 (configurable)                 │ │
│  │  - Accept multiple client connections                     │ │
│  │  - Async connection handling (asyncio)                    │ │
│  └───────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                  Frame Router / Multiplexer                │ │
│  │  - Bidirectional frame forwarding (no translation)        │ │
│  │  - Broadcast device → all TCP clients                     │ │
│  │  - Merge TCP client → device (first-come-first-served)    │ │
│  └───────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │               Backend Connection Manager                   │ │
│  │  - Single backend connection (Serial OR BLE)              │ │
│  │  - Auto-reconnect on disconnect                           │ │
│  │  - Health monitoring                                       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                      │                   │                       │
│         ┌────────────┘                   └────────────┐         │
│         ▼                                             ▼         │
│  ┌─────────────────┐                      ┌─────────────────┐  │
│  │ Serial Backend  │                      │  BLE Backend    │  │
│  │ - pyserial      │                      │  - bleak        │  │
│  │ - 115200 baud   │                      │  - async BLE    │  │
│  └─────────────────┘                      └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                      │                              │
                      ▼                              ▼
            ┌──────────────────┐         ┌──────────────────┐
            │  MeshCore Device │         │  MeshCore Device │
            │   (USB Serial)   │         │      (BLE)       │
            └──────────────────┘         └──────────────────┘
```

### Component Layers

1. **TCP Server Layer**
   - Listens for incoming TCP connections
   - Manages client lifecycle (connect/disconnect)
   - Maintains list of active clients

2. **Frame Router**
   - Forwards frames between backend and TCP clients
   - No protocol translation (pass-through)
   - Handles multiplexing for multiple clients

3. **Backend Manager**
   - Abstracts Serial/BLE connection
   - Auto-reconnect logic
   - Connection health monitoring

4. **Backend Implementations**
   - Serial: Uses pyserial/serial_asyncio
   - BLE: Uses bleak library

---

## Protocol Analysis

### MeshCore Framing Protocol

**Frame Structure** (identical across Serial, BLE, and TCP):
```
┌────────┬───────────┬───────────┬─────────────────────┐
│  0x3C  │  Size_Low │ Size_High │    Payload Data     │
│ (1B)   │   (1B)    │   (1B)    │   (Size bytes)      │
└────────┴───────────┴───────────┴─────────────────────┘

- Start Byte: 0x3C (60 decimal, '<' ASCII)
- Size: 2 bytes, little-endian (payload length)
- Payload: Variable length, MeshCore protocol data
```

**Example Frame**:
```
0x3C 0x05 0x00 0x01 0x02 0x03 0x04 0x05
│    │    │    └─────────────────────┘
│    │    │         5 bytes payload
│    │    └─ Size high byte (0)
│    └─ Size low byte (5)
└─ Start marker
```

### Frame Handling Code (from meshcore library)

Both `serial_cx.py` and `tcp_cx.py` use **identical** parsing logic:

```python
def handle_rx(self, data: bytearray):
    headerlen = len(self.header)
    framelen = len(self.inframe)
    if not self.frame_started:  # wait start of frame
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
            # Complete frame received - process it
            asyncio.create_task(self.reader.handle_rx(self.inframe))
            self.frame_started = False
            self.header = b""
            self.inframe = b""
            if framelen + len(data) > self.frame_size:
                self.handle_rx(data[self.frame_size - framelen :])
```

**Key Insight**: The proxy can use this code verbatim - no modification needed!

### Protocol Flow

```
MeshTUI (TCP Client)              Proxy                    MeshCore Device
        │                           │                              │
        │─────── connect() ─────────▶│                              │
        │                           │◀─── already connected ───────│
        │◀────── connected ──────────│                              │
        │                           │                              │
        │─── send_device_query() ───▶│                              │
        │     [0x3C 0x02 0x00        │                              │
        │      0x16 0x03]            │─────── forward frame ───────▶│
        │                           │                              │
        │                           │◀──── device_info response ────│
        │◀────── device_info ────────│                              │
        │                           │                              │
        │─── send_msg("Hi") ────────▶│─────── forward frame ───────▶│
        │                           │◀──── ack response ────────────│
        │◀────── ack ────────────────│                              │
```

No translation occurs - frames are forwarded byte-for-byte in both directions.

---

## Component Design

### 1. Main Proxy Class

**File**: `src/meshtui/proxy/proxy.py`

```python
class MeshCoreTCPProxy:
    """Main proxy daemon coordinating all components."""

    def __init__(self, config: ProxyConfig):
        self.config = config
        self.backend = None
        self.tcp_server = None
        self.tcp_clients = []
        self.running = False
        self.logger = logging.getLogger("meshcore.proxy")

    async def start(self):
        """Start the proxy daemon."""
        # 1. Initialize backend (Serial or BLE)
        # 2. Start TCP server
        # 3. Enter main loop

    async def stop(self):
        """Graceful shutdown."""
        # 1. Close all TCP clients
        # 2. Disconnect backend
        # 3. Stop TCP server

    async def handle_tcp_client(self, reader, writer):
        """Handle new TCP client connection."""
        # Add to client list
        # Start forwarding task

    async def forward_backend_to_tcp(self, frame: bytes):
        """Broadcast frame from backend to all TCP clients."""
        # Send to all connected clients

    async def forward_tcp_to_backend(self, client_id: str, frame: bytes):
        """Forward frame from TCP client to backend."""
        # Send to backend device
```

### 2. Backend Interface

**File**: `src/meshtui/proxy/backends/__init__.py`

```python
class Backend(ABC):
    """Abstract backend interface."""

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to device."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Disconnect from device."""
        pass

    @abstractmethod
    async def send_frame(self, frame: bytes):
        """Send frame to device."""
        pass

    @abstractmethod
    def set_frame_callback(self, callback: Callable[[bytes], Awaitable[None]]):
        """Set callback for received frames."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check connection status."""
        pass
```

### 3. Serial Backend

**File**: `src/meshtui/proxy/backends/serial.py`

```python
class SerialBackend(Backend):
    """Serial port backend using pyserial."""

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.transport = None
        self.protocol = None
        self.frame_callback = None

        # Frame parsing state (copied from meshcore)
        self.frame_started = False
        self.frame_size = 0
        self.header = b""
        self.inframe = b""

    async def connect(self) -> bool:
        """Open serial port."""
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await serial_asyncio.create_serial_connection(
            loop,
            lambda: SerialProtocol(self),
            self.port,
            baudrate=self.baudrate
        )
        return True

    def handle_rx(self, data: bytes):
        """Parse incoming data (copied from meshcore)."""
        # Use exact same frame parsing logic
        # When complete frame received, call self.frame_callback(frame)

    async def send_frame(self, frame: bytes):
        """Send frame to serial device."""
        pkt = b"\x3c" + len(frame).to_bytes(2, "little") + frame
        self.transport.write(pkt)
```

### 4. BLE Backend

**File**: `src/meshtui/proxy/backends/ble.py`

```python
class BLEBackend(Backend):
    """BLE backend using bleak."""

    def __init__(self, address: str):
        self.address = address
        self.client = None
        self.frame_callback = None

        # Frame parsing state
        self.frame_started = False
        self.frame_size = 0
        self.header = b""
        self.inframe = b""

        # BLE characteristics (from meshcore)
        self.TX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
        self.RX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

    async def connect(self) -> bool:
        """Connect to BLE device."""
        self.client = BleakClient(self.address)
        await self.client.connect()
        await self.client.start_notify(self.RX_CHAR_UUID, self._notification_handler)
        return True

    def _notification_handler(self, sender, data):
        """Handle BLE notification."""
        self.handle_rx(data)

    def handle_rx(self, data: bytes):
        """Parse incoming data (same as serial)."""
        # Use exact same frame parsing logic

    async def send_frame(self, frame: bytes):
        """Send frame via BLE."""
        pkt = b"\x3c" + len(frame).to_bytes(2, "little") + frame
        await self.client.write_gatt_char(self.TX_CHAR_UUID, pkt)
```

### 5. TCP Server

**File**: `src/meshtui/proxy/tcp_server.py`

```python
class TCPServer:
    """TCP server for client connections."""

    def __init__(self, host: str, port: int, proxy):
        self.host = host
        self.port = port
        self.proxy = proxy
        self.server = None
        self.clients = {}  # reader -> writer

    async def start(self):
        """Start listening for connections."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port
        )
        logger.info(f"TCP server listening on {self.host}:{self.port}")

    async def _handle_client(self, reader, writer):
        """Handle individual TCP client."""
        addr = writer.get_extra_info('peername')
        logger.info(f"New client connected: {addr}")

        self.clients[reader] = writer

        try:
            while True:
                # Read frames from TCP client
                frame = await self._read_frame(reader)
                if not frame:
                    break

                # Forward to backend
                await self.proxy.backend.send_frame(frame)

        except Exception as e:
            logger.error(f"Client {addr} error: {e}")
        finally:
            del self.clients[reader]
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client disconnected: {addr}")

    async def _read_frame(self, reader) -> bytes:
        """Read one complete frame from TCP client."""
        # Read header (3 bytes)
        header = await reader.readexactly(3)
        if header[0] != 0x3C:
            raise ValueError("Invalid frame start marker")

        size = int.from_bytes(header[1:3], "little")
        payload = await reader.readexactly(size)
        return payload

    async def broadcast_frame(self, frame: bytes):
        """Send frame to all connected clients."""
        pkt = b"\x3c" + len(frame).to_bytes(2, "little") + frame

        for writer in self.clients.values():
            try:
                writer.write(pkt)
                await writer.drain()
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
```

### 6. Configuration Manager

**File**: `src/meshtui/proxy/config.py`

```python
from dataclasses import dataclass
from typing import Optional
import yaml

@dataclass
class ProxyConfig:
    """Proxy configuration."""

    # TCP Server
    listen_host: str = "0.0.0.0"
    listen_port: int = 5000

    # Backend
    backend_type: str = "serial"  # 'serial' or 'ble'

    # Serial backend
    serial_port: Optional[str] = None
    serial_baudrate: int = 115200

    # BLE backend
    ble_address: Optional[str] = None

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    @classmethod
    def from_yaml(cls, path: str) -> 'ProxyConfig':
        """Load config from YAML file."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        return cls(
            listen_host=data['proxy'].get('listen_host', '0.0.0.0'),
            listen_port=data['proxy'].get('listen_port', 5000),
            backend_type=data['backend']['type'],
            serial_port=data['backend'].get('serial_port'),
            serial_baudrate=data['backend'].get('baudrate', 115200),
            ble_address=data['backend'].get('ble_address'),
            log_level=data['logging'].get('level', 'INFO'),
            log_file=data['logging'].get('file'),
        )

    def validate(self):
        """Validate configuration."""
        if self.backend_type == 'serial' and not self.serial_port:
            raise ValueError("serial_port required for serial backend")

        if self.backend_type == 'ble' and not self.ble_address:
            raise ValueError("ble_address required for BLE backend")
```

### 7. CLI Entry Point

**File**: `src/meshtui/proxy/__main__.py`

```python
import argparse
import asyncio
import logging
import signal
import sys

from .proxy import MeshCoreTCPProxy
from .config import ProxyConfig

def main():
    parser = argparse.ArgumentParser(description="MeshCore TCP Proxy")
    parser.add_argument(
        '--config', '-c',
        default='/etc/meshcore-proxy/config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--serial', '-s',
        help='Serial port (overrides config file)'
    )
    parser.add_argument(
        '--ble', '-b',
        help='BLE address (overrides config file)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        help='TCP listen port (default: 5000)'
    )
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='Run as daemon (background)'
    )

    args = parser.parse_args()

    # Load configuration
    try:
        config = ProxyConfig.from_yaml(args.config)
    except FileNotFoundError:
        # Use defaults
        config = ProxyConfig()

    # Override with CLI arguments
    if args.serial:
        config.backend_type = 'serial'
        config.serial_port = args.serial

    if args.ble:
        config.backend_type = 'ble'
        config.ble_address = args.ble

    if args.port:
        config.listen_port = args.port

    # Validate
    config.validate()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(config.log_file) if config.log_file else logging.NullHandler()
        ]
    )

    logger = logging.getLogger("meshcore.proxy")
    logger.info(f"Starting MeshCore TCP Proxy")
    logger.info(f"Backend: {config.backend_type}")
    logger.info(f"Listening on {config.listen_host}:{config.listen_port}")

    # Create and start proxy
    proxy = MeshCoreTCPProxy(config)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(proxy.stop()))

    try:
        loop.run_until_complete(proxy.start())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        loop.run_until_complete(proxy.stop())

if __name__ == '__main__':
    main()
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (4-6 hours)

**Goal**: Working proxy with Serial backend, single TCP client

1. **Project Setup** (30 min)
   ```bash
   cd meshtui  # Already in meshtui repository
   source venv/bin/activate  # Use existing venv

   # Create directory structure for proxy component
   mkdir -p src/meshtui/proxy/backends
   mkdir -p tests/proxy
   mkdir -p config/proxy
   touch src/meshtui/proxy/__init__.py
   touch src/meshtui/proxy/backends/__init__.py
   ```

2. **Configuration Module** (1 hour)
   - Implement `config.py`
   - Create example `config.yaml`
   - Add validation logic

3. **Serial Backend** (2 hours)
   - Implement `backends/serial.py`
   - Copy frame parsing from meshcore
   - Test with direct serial connection
   - Verify frame reception/transmission

4. **TCP Server** (1.5 hours)
   - Implement `tcp_server.py`
   - Single client support initially
   - Frame reading/writing
   - Basic error handling

5. **Main Proxy Orchestration** (1 hour)
   - Implement `proxy.py`
   - Connect backend → TCP forwarding
   - Connect TCP → backend forwarding
   - Startup/shutdown logic

6. **CLI Entry Point** (30 min)
   - Implement `__main__.py`
   - Argument parsing
   - Logging setup

7. **Testing** (30 min)
   - Test with meshtui TCP connection
   - Verify commands work end-to-end
   - Check frame integrity

### Phase 2: Multi-Client Support (2-3 hours)

**Goal**: Support multiple simultaneous meshtui connections

1. **Client Session Management** (1 hour)
   - Track multiple clients in TCP server
   - Per-client state tracking
   - Graceful disconnect handling

2. **Frame Broadcasting** (1 hour)
   - Send backend frames to all clients
   - Handle slow clients (buffering)
   - Client removal on error

3. **Testing** (1 hour)
   - Connect multiple meshtui instances
   - Verify all receive updates
   - Test disconnect scenarios

### Phase 3: BLE Backend (2-4 hours)

**Goal**: Add BLE device support

1. **BLE Backend Implementation** (2 hours)
   - Implement `backends/ble.py`
   - BleakClient integration
   - Notification handling
   - Same frame parsing logic

2. **Backend Selector** (30 min)
   - Factory pattern for backend creation
   - Runtime selection based on config

3. **Testing** (1 hour)
   - Test with BLE-connected device
   - Verify same behavior as serial
   - Test reconnection

### Phase 4: Robustness & Polish (2-3 hours)

**Goal**: Production-ready reliability

1. **Auto-Reconnect** (1 hour)
   - Backend reconnection on disconnect
   - Exponential backoff
   - Status logging

2. **Health Monitoring** (30 min)
   - Backend connection status
   - Client connection status
   - Periodic health checks

3. **Error Handling** (1 hour)
   - Comprehensive try-catch blocks
   - Graceful degradation
   - Clear error messages

4. **Logging Enhancement** (30 min)
   - Structured logging
   - Debug level frame dumps
   - Performance metrics

### Phase 5: Daemon & Packaging (2-3 hours)

**Goal**: System integration and distribution

1. **Systemd Service** (1 hour)
   - Create `.service` file
   - Installation script
   - Log rotation config

2. **PyPI Packaging** (1 hour)
   - Complete `pyproject.toml`
   - Build metadata
   - README and docs

3. **Installation Documentation** (1 hour)
   - Quick start guide
   - Configuration examples
   - Troubleshooting guide

### Total Estimated Time

- **Phase 1 (MVP)**: 4-6 hours ⭐ **Start here**
- **Phase 2**: 2-3 hours
- **Phase 3**: 2-4 hours
- **Phase 4**: 2-3 hours
- **Phase 5**: 2-3 hours

**Grand Total**: 12-19 hours

---

## Configuration

### Example Configuration File

**File**: `config/config.yaml`

```yaml
# MeshCore TCP Proxy Configuration

proxy:
  # TCP server listen address (0.0.0.0 = all interfaces)
  listen_host: 0.0.0.0

  # TCP server listen port
  listen_port: 5000

  # Maximum number of concurrent clients (0 = unlimited)
  max_clients: 5

backend:
  # Backend type: 'serial' or 'ble'
  type: serial

  # Serial backend configuration
  serial_port: /dev/ttyUSB0
  baudrate: 115200

  # BLE backend configuration (alternative to serial)
  # ble_address: "C2:2B:A1:D5:3E:B6"

  # Auto-reconnect on disconnect
  auto_reconnect: true
  reconnect_delay: 5  # seconds
  max_reconnect_attempts: 0  # 0 = infinite

logging:
  # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: INFO

  # Log file path (null = stdout only)
  file: /var/log/meshcore-proxy/proxy.log

  # Log rotation
  max_bytes: 10485760  # 10MB
  backup_count: 5

  # Log frame data (verbose, for debugging)
  log_frames: false

security:
  # Bind to localhost only for local access
  # localhost_only: true

  # Optional: allowed client IP addresses (empty = all)
  # allowed_ips:
  #   - 192.168.1.0/24
  #   - 10.0.0.0/8
```

### Configuration for Different Scenarios

**Scenario 1: Local USB Serial Device**
```yaml
proxy:
  listen_host: 127.0.0.1  # localhost only
  listen_port: 5000

backend:
  type: serial
  serial_port: /dev/ttyUSB0
```

**Scenario 2: BLE Device with Network Access**
```yaml
proxy:
  listen_host: 0.0.0.0  # all interfaces
  listen_port: 5000

backend:
  type: ble
  ble_address: "C2:2B:A1:D5:3E:B6"
```

**Scenario 3: Development/Debug Mode**
```yaml
proxy:
  listen_host: 0.0.0.0
  listen_port: 5000

backend:
  type: serial
  serial_port: /dev/ttyUSB0

logging:
  level: DEBUG
  log_frames: true
  file: ./proxy-debug.log
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_frame_parsing.py`

```python
import pytest
from meshtui.proxy.backends.serial import SerialBackend

def test_single_frame_parsing():
    """Test parsing a complete frame."""
    backend = SerialBackend("/dev/null")

    received_frames = []
    backend.set_frame_callback(lambda f: received_frames.append(f))

    # Send complete frame: 0x3C 0x03 0x00 0x01 0x02 0x03
    data = bytes([0x3C, 0x03, 0x00, 0x01, 0x02, 0x03])
    backend.handle_rx(data)

    assert len(received_frames) == 1
    assert received_frames[0] == bytes([0x01, 0x02, 0x03])

def test_fragmented_frame():
    """Test parsing frame received in multiple chunks."""
    backend = SerialBackend("/dev/null")

    received_frames = []
    backend.set_frame_callback(lambda f: received_frames.append(f))

    # Send in fragments
    backend.handle_rx(bytes([0x3C]))  # Start
    backend.handle_rx(bytes([0x03]))  # Size low
    backend.handle_rx(bytes([0x00]))  # Size high
    backend.handle_rx(bytes([0x01, 0x02]))  # Partial payload
    backend.handle_rx(bytes([0x03]))  # Final byte

    assert len(received_frames) == 1
    assert received_frames[0] == bytes([0x01, 0x02, 0x03])

def test_multiple_frames_in_buffer():
    """Test parsing multiple frames received together."""
    backend = SerialBackend("/dev/null")

    received_frames = []
    backend.set_frame_callback(lambda f: received_frames.append(f))

    # Two complete frames in one buffer
    data = bytes([
        0x3C, 0x02, 0x00, 0x01, 0x02,  # Frame 1
        0x3C, 0x03, 0x00, 0x03, 0x04, 0x05  # Frame 2
    ])
    backend.handle_rx(data)

    assert len(received_frames) == 2
    assert received_frames[0] == bytes([0x01, 0x02])
    assert received_frames[1] == bytes([0x03, 0x04, 0x05])
```

### Integration Tests

**File**: `tests/test_integration.py`

```python
import pytest
import asyncio
from meshtui.proxy.proxy import MeshCoreTCPProxy
from meshtui.proxy.config import ProxyConfig

@pytest.mark.asyncio
async def test_tcp_client_connection():
    """Test that TCP clients can connect."""
    config = ProxyConfig(
        backend_type='serial',
        serial_port='/dev/ttyUSB0',
        listen_port=15000  # Use non-standard port for testing
    )

    proxy = MeshCoreTCPProxy(config)

    # Start proxy in background
    proxy_task = asyncio.create_task(proxy.start())
    await asyncio.sleep(1)  # Give time to start

    # Connect TCP client
    reader, writer = await asyncio.open_connection('localhost', 15000)

    # Verify connection
    assert not writer.is_closing()

    # Cleanup
    writer.close()
    await writer.wait_closed()
    await proxy.stop()
    proxy_task.cancel()

@pytest.mark.asyncio
async def test_frame_forwarding():
    """Test that frames are forwarded correctly."""
    # TODO: Mock backend and verify frame forwarding
    pass
```

### Manual Testing Checklist

**Phase 1 - Basic Functionality**
- [ ] Proxy starts without errors
- [ ] Backend connects to device
- [ ] TCP server accepts connections
- [ ] MeshTUI can connect via TCP
- [ ] Device query works
- [ ] Send message works
- [ ] Receive message works
- [ ] Disconnect/reconnect works

**Phase 2 - Multi-Client**
- [ ] Two meshtui instances connect simultaneously
- [ ] Both receive messages
- [ ] Both can send messages
- [ ] One client disconnect doesn't affect other

**Phase 3 - BLE Backend**
- [ ] BLE device discovered
- [ ] BLE connection established
- [ ] Same functionality as Serial
- [ ] BLE disconnection handled

**Phase 4 - Robustness**
- [ ] Backend disconnect/reconnect works
- [ ] Network interruption handled gracefully
- [ ] Memory usage stays stable over time
- [ ] No file descriptor leaks
- [ ] Error messages are clear

**Phase 5 - Deployment**
- [ ] Systemd service starts at boot
- [ ] Logs rotate correctly
- [ ] Configuration changes take effect
- [ ] pip/pipx installation works

---

## Future Enhancements

### Priority 1: Core Features

1. **Auto-Discovery**
   - Scan for available serial ports
   - Auto-detect MeshCore devices
   - BLE device scanning
   - Selection UI or config priority

2. **Connection Status API**
   - HTTP endpoint for status
   - JSON metrics (uptime, clients, backend health)
   - Prometheus metrics export

3. **Multiple Device Support**
   - Run multiple proxy instances (different ports)
   - Single daemon managing multiple devices
   - Load balancing across devices

### Priority 2: Security

1. **Authentication**
   - API key authentication for TCP clients
   - TLS/SSL support for encrypted connections
   - Client certificate authentication

2. **Access Control**
   - IP whitelist/blacklist
   - Per-client rate limiting
   - Command filtering/restrictions

3. **Audit Logging**
   - Log all commands and responses
   - Client activity tracking
   - Security event notifications

### Priority 3: Management

1. **Web UI**
   - Configuration management
   - Real-time status dashboard
   - Log viewer
   - Client management
   - **Firmware update interface** (see detailed analysis below)

2. **REST API**
   - Start/stop proxy
   - Reconnect backend
   - Kick clients
   - Query statistics

3. **Monitoring Integration**
   - Prometheus exporter
   - Grafana dashboard
   - Health check endpoint
   - Alerting hooks

### Priority 4: Advanced Features

1. **Frame Recording/Replay**
   - Record all traffic to file
   - Replay for testing/debugging
   - Frame inspection tools

2. **Protocol Analysis**
   - Decode and display MeshCore protocol
   - Statistics on command types
   - Performance profiling

3. **High Availability**
   - Failover between multiple backends
   - Clustering for redundancy
   - State synchronization

---

## Firmware Update via Web Frontend

**Status**: Future Enhancement (Priority 3)
**Feasibility**: ✅ Technically Feasible (with caveats)

### Overview

Adding firmware update capability to the proxy web frontend would allow users to download the latest stable firmware for their device and flash it directly through the web interface. This feature would:

- Detect device model and current firmware version
- Check for available updates from firmware repository
- Guide users through the flashing process
- Provide safety checks and verification

### Current Device Info Capabilities

The MeshCore `ver` command (device query) already provides:
```python
{
    "fw ver": 3,              # Firmware protocol version
    "max_contacts": 256,      # Device capabilities
    "max_channels": 8,
    "ble_pin": 123456,
    "fw_build": "2024-10-15",  # Build date
    "model": "Heltec V3",      # Hardware model
    "ver": "1.2.3"            # Firmware version string
}
```

**Key Insight**: We can identify current firmware version and hardware model, allowing us to determine if an update is available.

### Implementation Challenge

**The MeshCore protocol does not currently expose firmware flashing commands.** After analyzing the meshcore Python library, there are:
- No `flash_firmware()` methods
- No `BinaryReqType.FIRMWARE_UPDATE` packet types
- No bootloader access commands

All communication uses high-level framed packets for messaging, contacts, and device configuration—but not firmware updates.

### Implementation Options

#### Option 1: Low-Level Serial Bootloader Access

**Description**: Bypass the MeshCore protocol and communicate directly with the device bootloader (ESP32/RP2040).

**Feasibility**: ⚠️ Technically possible, operationally complex

**Approach**:
1. Device reboots into bootloader mode (ESP32 ROM bootloader, etc.)
2. Proxy releases serial port temporarily
3. Use `esptool.py` library for ESP32 flashing directly
4. Resume proxy connection after flash completes

**Pros**:
- Works with existing firmware (no API changes needed)
- Full control over flash process
- Can recover from bad firmware

**Cons**:
- Only works with serial backend (not BLE or TCP)
- Requires hardware control (DTR/RTS lines for bootloader entry)
- Complex error handling and recovery
- Hardware-specific (ESP32 vs RP2040 vs others)
- Risk of bricking device if interrupted

**Estimated Effort**: 7-10 days

#### Option 2: MeshCore API Extension (Upstream)

**Description**: Add firmware update commands to the MeshCore firmware protocol itself.

**Feasibility**: ✅ Clean design, ❌ Requires upstream changes

**Approach**:
1. Add new packet types: `FIRMWARE_START`, `FIRMWARE_CHUNK`, `FIRMWARE_END`, `FIRMWARE_STATUS`
2. Implement OTA update handler in device firmware
3. Update Python library with `DeviceCommands.update_firmware()` method
4. Chunked transfer with progress callbacks

**Pros**:
- Clean API integration
- Works over all transport types (Serial, BLE, TCP)
- Safe rollback possible
- Consistent with MeshCore design philosophy

**Cons**:
- Requires upstream MeshCore firmware changes
- Long development cycle (1-2 weeks firmware + testing)
- Can't update devices with old firmware (chicken-and-egg)
- Needs buy-in from MeshCore maintainers

**Estimated Effort**: 3-4 weeks (plus upstream coordination)

#### Option 3: Serial Passthrough Mode (⭐ Recommended)

**Description**: Proxy temporarily yields serial port control to allow external flashing tools.

**Feasibility**: ✅ Practical and safe

**Approach**:
1. **Passthrough API**:
   - Web API endpoint: `POST /api/flash/begin` → Proxy closes serial connection
   - Returns: `{"status": "passthrough", "serial_port": "/dev/ttyUSB0"}`
   - Proxy stops reading from serial

2. **Web Serial API** (Modern browsers):
   ```javascript
   // Browser can directly access serial port
   const port = await navigator.serial.requestPort();
   await port.open({ baudRate: 115200 });

   // Use web-based esptool.js library
   await flashFirmware(port, firmwareBinary);
   ```

3. **Firmware download**:
   - Web frontend fetches from GitHub releases
   - Filters by device model (from `ver` command)
   - Displays changelog and version info

4. **Resume proxy**:
   - `POST /api/flash/resume` → Proxy reopens serial connection
   - Normal operation continues

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                    Web Frontend                             │
│  1. Fetch device info (model, current version)             │
│  2. Query GitHub for latest firmware                        │
│  3. Request passthrough mode from proxy                     │
│  4. Flash via Web Serial API (browser-native)               │
│  5. Resume proxy connection                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  Proxy Web API                              │
│  - GET /api/device/info  → Device model, version           │
│  - POST /api/flash/begin → Close serial, return port path  │
│  - POST /api/flash/resume → Reopen serial connection        │
└─────────────────────────────────────────────────────────────┘
                           ↓
                   Serial Device (Direct)
```

**Pros**:
- No firmware changes needed
- Works immediately with current devices
- Leverages well-tested tools (esptool.py/esptool.js)
- Web Serial API = no CLI needed (modern browsers)
- Safe (external tools have proven error handling)

**Cons**:
- Proxy unavailable during flash operation
- Web Serial API requires HTTPS or localhost
- Only works with serial backend (not BLE)
- Slightly more complex UX (multi-step process)

**Estimated Effort**: 7-10 days

### Firmware Repository Strategy

Regardless of implementation option, we need a firmware source:

#### GitHub Releases Approach
```javascript
// Fetch latest firmware for device model
const releases = await fetch(
  'https://api.github.com/repos/meshcore/firmware/releases'
);
const latest = releases.find(r => !r.prerelease);
const assets = latest.assets.filter(a =>
  a.name.includes(deviceModel)
);
```

#### Firmware Manifest
```json
{
  "version": "1.3.0",
  "build_date": "2025-10-21",
  "models": [
    {
      "name": "Heltec V3",
      "url": "https://github.com/.../heltec-v3-1.3.0.bin",
      "checksum": "sha256:abc123...",
      "min_version": "1.0.0"
    }
  ],
  "changelog": "- Added firmware update API\n- Fixed GPS sync..."
}
```

#### Update Check Logic
```python
current_version = device_info["ver"]  # "1.2.3"
latest_version = fetch_latest_version(device_info["model"])

if version_compare(latest_version, current_version) > 0:
    return {"update_available": True, "latest": latest_version}
```

### Security Considerations

#### Firmware Verification
- **SHA256 checksums**: Verify downloaded firmware integrity
- **Signature validation**: Check signed releases (if available)
- **HTTPS only**: Use secure transport for downloads

#### User Safety
- **Battery check**: Require >50% battery before flash
- **Backup warning**: Warn about potential data loss
- **Confirmation dialogs**: Multi-step confirmation (model, version, risks)
- **Timeout protection**: Abort if flash takes too long

#### Proxy Security
- **Authentication**: Require auth for flash operations
- **Rate limiting**: Prevent spam/abuse attempts
- **Audit logging**: Log all flash attempts with timestamps

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Device bricking | Low | Critical | Battery checks, checksums, tested tools |
| Interrupted flash | Medium | High | Bootloader recovery mode, user warnings |
| Wrong firmware | Low | Critical | Model verification, explicit confirmation |
| Proxy deadlock | Medium | Medium | Timeout mechanisms, manual resume endpoint |
| Web Serial incompatibility | Low | Medium | Fallback to CLI guidance instructions |

### Recommended Implementation Plan

#### Phase 1: Foundation (Web Frontend MVP)
**Goal**: Build web UI for proxy management

**Features**:
1. Create basic web frontend (React/Vue/Vanilla JS)
2. Display device info (model, version, connection status)
3. Show connected clients list
4. Basic controls (reconnect, view logs)

**Estimated**: 5-7 days

#### Phase 2: Firmware Update (Passthrough Mode)
**Goal**: Enable firmware flashing capability

**Features**:
1. Add proxy passthrough API endpoints
2. Implement GitHub releases integration
3. Add Web Serial API flash workflow
4. Safety checks and user confirmations
5. Progress indicators and status updates

**Estimated**: 7-10 days

#### Phase 3: Enhancement (Optional)
**Goal**: Improve UX and automation

**Features**:
1. Automatic update checks on connection
2. Scheduled update prompts
3. Firmware rollback capability
4. Multi-device management interface

**Estimated**: 5-7 days

### Web Frontend Technology Stack

**Recommended**: Vanilla JavaScript or lightweight framework

**Rationale**:
- Simple single-page application
- No complex state management needed
- Minimal bundle size
- Easy to package with proxy

**Alternative**: React/Vue if expanding to full device management suite

**Key Libraries**:
- **Web Serial API**: Native browser support (Chrome, Edge, Opera)
- **esptool-js**: Web-based ESP32 flashing library
- **Axios/Fetch**: API communication
- **Chart.js**: Real-time statistics (optional)

### Conclusion

**Firmware update via TCP proxy web frontend is feasible and recommended** using **Option 3: Serial Passthrough with Web Serial API**.

**Key Advantages**:
- ✅ No firmware changes required
- ✅ Works with existing devices immediately
- ✅ Leverages proven flashing tools
- ✅ Modern browser-native experience
- ✅ Reasonable development time (7-10 days)

**Next Steps**:
1. Implement basic web frontend (Phase 1)
2. Add passthrough mode to proxy API
3. Integrate Web Serial API
4. Set up firmware repository/manifest
5. Test extensively with multiple device models

Once a web frontend exists, other management features become easier to add:
- Real-time device monitoring dashboard
- Configuration backup/restore
- Multi-device fleet management
- Firmware rollback capability
- Automatic update notifications
- Usage statistics and telemetry

This provides a solid foundation for a comprehensive device management system while remaining practical to implement.

---

## References

### MeshCore Protocol Documentation

- **Frame Format**: See `docs/meshcore-api/serial_cx.py` and `tcp_cx.py`
- **Protocol Commands**: See `docs/meshcore-api/commands/`
- **Event Types**: See `docs/meshcore-api/events.py`

### Key Files in MeshTUI Repository

- `src/meshtui/connection.py` - Connection orchestration
- `src/meshtui/transport.py` - Transport layer abstractions
- `docs/meshcore-api/serial_cx.py` - Serial connection implementation
- `docs/meshcore-api/tcp_cx.py` - TCP connection implementation
- `docs/meshcore-api/ble_cx.py` - BLE connection implementation

### External Dependencies

- **pyserial** / **pyserial-asyncio**: Serial port communication
  - Docs: https://pyserial.readthedocs.io/
  - Async: https://pyserial-asyncio.readthedocs.io/

- **bleak**: Cross-platform BLE library
  - Docs: https://bleak.readthedocs.io/
  - GitHub: https://github.com/hbldh/bleak

- **pyyaml**: YAML configuration parsing
  - Docs: https://pyyaml.org/

- **asyncio**: Python async I/O framework
  - Docs: https://docs.python.org/3/library/asyncio.html

### Similar Projects

- **ser2net**: Serial port to network proxy (C implementation)
- **socat**: Generic bidirectional data relay (supports serial/TCP)
- **PyProxy**: Python-based protocol proxy framework

---

## Appendix A: Project File Structure

The proxy will be integrated into the meshtui repository structure:

```
meshtui/
├── src/
│   └── meshtui/
│       ├── __init__.py
│       ├── __main__.py          # MeshTUI main entry point
│       ├── app.py
│       ├── connection.py
│       ├── ... (other meshtui files)
│       │
│       └── proxy/               # NEW: TCP Proxy component
│           ├── __init__.py
│           ├── __main__.py      # Proxy CLI entry point
│           ├── proxy.py         # Main proxy class
│           ├── tcp_server.py    # TCP server implementation
│           ├── config.py        # Configuration management
│           │
│           └── backends/
│               ├── __init__.py  # Backend interface
│               ├── serial.py    # Serial backend
│               └── ble.py       # BLE backend
│
├── tests/
│   ├── ... (existing meshtui tests)
│   │
│   └── proxy/                   # NEW: Proxy tests
│       ├── __init__.py
│       ├── test_frame_parsing.py
│       ├── test_backends.py
│       ├── test_tcp_server.py
│       └── test_integration.py
│
├── config/
│   └── proxy/                   # NEW: Proxy configuration examples
│       ├── config.yaml.example
│       ├── config-serial.yaml
│       ├── config-ble.yaml
│       └── meshcore-proxy.service  # Systemd unit file
│
├── docs/
│   ├── MESHCORE_TCP_PROXY_DESIGN.md  # This document
│   ├── ... (other docs)
│
├── pyproject.toml               # Updated with [proxy] optional dependency
├── README.md
└── LICENSE
```

---

## Appendix B: pyproject.toml Integration

The proxy will be integrated into meshtui's existing `pyproject.toml` as an optional component:

```toml
# Add to meshtui's pyproject.toml

[project.optional-dependencies]
# Existing optional dependencies...

# TCP Proxy component
proxy = [
    "pyserial>=3.5",
    "pyserial-asyncio>=0.6",
    "bleak>=0.21.0",
    "pyyaml>=6.0",
]

[project.scripts]
meshtui = "meshtui.__main__:main"
meshcore-tcp-proxy = "meshtui.proxy.__main__:main"  # New proxy entry point

[project.urls]
Homepage = "https://github.com/ekollof/meshtui"
Repository = "https://github.com/ekollof/meshtui"
Documentation = "https://github.com/ekollof/meshtui/tree/master/docs"
"Bug Tracker" = "https://github.com/ekollof/meshtui/issues"

[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.black]
line-length = 100
target-version = ['py310']

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I"]
ignore = []
```

---

## Appendix C: Systemd Service File

**File**: `config/meshcore-proxy.service`

```ini
[Unit]
Description=MeshCore TCP Proxy
Documentation=https://github.com/yourusername/meshcore-tcp-proxy
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=meshcore
Group=meshcore
WorkingDirectory=/opt/meshcore-proxy

# Configuration file location
Environment="CONFIG_FILE=/etc/meshcore-proxy/config.yaml"

# Run the proxy
ExecStart=/usr/local/bin/meshcore-tcp-proxy --config ${CONFIG_FILE}

# Restart behavior
Restart=on-failure
RestartSec=5s
StartLimitInterval=300
StartLimitBurst=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=meshcore-proxy

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/meshcore-proxy

# Device access (for serial/BLE)
SupplementaryGroups=dialout bluetooth
DevicePolicy=closed
DeviceAllow=/dev/ttyUSB0 rw
DeviceAllow=/dev/ttyACM0 rw
DeviceAllow=/dev/rfcomm0 rw

[Install]
WantedBy=multi-user.target
```

**Installation**:
```bash
# Copy service file
sudo cp config/meshcore-proxy.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start at boot)
sudo systemctl enable meshcore-proxy

# Start service
sudo systemctl start meshcore-proxy

# Check status
sudo systemctl status meshcore-proxy

# View logs
sudo journalctl -u meshcore-proxy -f
```

---

## Appendix D: Quick Start Commands

### Installation

```bash
# Install meshtui with proxy component
pip install meshtui[proxy]
# or
pipx install meshtui[proxy]

# For development (from source)
git clone https://github.com/ekollof/meshtui.git
cd meshtui
pip install -e .[proxy]
```

### Basic Usage

```bash
# Start with serial device
meshcore-tcp-proxy --serial /dev/ttyUSB0

# Start with BLE device
meshcore-tcp-proxy --ble C2:2B:A1:D5:3E:B6

# Start with config file
meshcore-tcp-proxy --config /etc/meshcore-proxy/config.yaml

# Start on custom port
meshcore-tcp-proxy --serial /dev/ttyUSB0 --port 6000

# Run as daemon
meshcore-tcp-proxy --daemon --config /etc/meshcore-proxy/config.yaml
```

### Testing Connection

```bash
# Using meshtui
meshtui --tcp localhost:5000

# Using netcat to test connectivity
nc localhost 5000

# Using telnet
telnet localhost 5000
```

---

## Document Revision History

| Version | Date       | Author | Changes                          |
|---------|------------|--------|----------------------------------|
| 1.0     | 2025-10-21 | Claude | Initial design document          |

---

**End of Design Document**
