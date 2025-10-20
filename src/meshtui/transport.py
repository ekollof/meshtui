#!/usr/bin/env python3
"""
Transport layer abstraction for MeshCore connections.
Handles BLE, Serial, and TCP connections.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

import serial.tools.list_ports
from bleak import BleakScanner
from meshcore import MeshCore, EventType


class ConnectionType(Enum):
    """Types of connections supported."""

    BLE = "ble"
    TCP = "tcp"
    SERIAL = "serial"


class SerialTransport:
    """Handles serial port connections to MeshCore devices."""

    def __init__(self):
        self.logger = logging.getLogger("meshtui.transport.serial")

    async def identify_device(
        self, device_path: str, timeout: float = 5.0, retries: int = 2
    ) -> bool:
        """Identify if a serial device is a MeshCore device.

        Args:
            device_path: Path to the serial device
            timeout: Timeout for identification attempt (default: 5.0s)
            retries: Number of retry attempts (default: 2)

        Returns:
            True if device is MeshCore, False otherwise
        """
        for attempt in range(retries):
            temp_mc = None
            try:
                if attempt > 0:
                    self.logger.debug(f"Retry {attempt} for {device_path}...")
                    # Wait a bit between retries to let serial port settle
                    await asyncio.sleep(0.5)

                self.logger.debug(
                    f"Testing if {device_path} is a MeshCore device (attempt {attempt + 1}/{retries})..."
                )

                # Create a temporary connection to test
                temp_mc = await MeshCore.create_serial(
                    port=device_path, baudrate=115200, debug=False, only_error=True
                )

                # Give the device a moment to initialize
                await asyncio.sleep(0.2)

                # Query device info with timeout
                result = await asyncio.wait_for(
                    temp_mc.commands.send_device_query(), timeout=timeout
                )

                # Check if we got valid device info
                if result.type == EventType.ERROR:
                    self.logger.debug(
                        f"{device_path} returned error on query (attempt {attempt + 1}/{retries})"
                    )
                    await temp_mc.disconnect()
                    # Give asyncio time to clean up tasks
                    await asyncio.sleep(0.1)
                    temp_mc = None
                    continue  # Try again

                # Check for valid MeshCore response
                device_info = result.payload
                if device_info and "model" in device_info:
                    self.logger.info(
                        f"✓ Found MeshCore device at {device_path}: {device_info.get('model')} v{device_info.get('ver', 'unknown')}"
                    )
                    await temp_mc.disconnect()
                    # Give asyncio time to clean up tasks
                    await asyncio.sleep(0.1)
                    return True
                else:
                    self.logger.debug(
                        f"{device_path} responded but lacks MeshCore identification"
                    )
                    await temp_mc.disconnect()
                    # Give asyncio time to clean up tasks
                    await asyncio.sleep(0.1)
                    temp_mc = None
                    continue  # Try again

            except asyncio.TimeoutError:
                self.logger.debug(
                    f"Timeout identifying {device_path} (attempt {attempt + 1}/{retries})"
                )
                if temp_mc:
                    try:
                        await temp_mc.disconnect()
                        # Give asyncio time to clean up tasks
                        await asyncio.sleep(0.1)
                    except Exception:
                        pass
                continue  # Try again
            except Exception as e:
                self.logger.debug(
                    f"Failed to identify {device_path} (attempt {attempt + 1}/{retries}): {e}"
                )
                if temp_mc:
                    try:
                        await temp_mc.disconnect()
                        # Give asyncio time to clean up tasks
                        await asyncio.sleep(0.1)
                    except Exception:
                        pass
                continue  # Try again

        # All retries failed
        self.logger.debug(
            f"✗ {device_path} is not a MeshCore device after {retries} attempts"
        )
        return False

    async def list_ports(self) -> List[Dict[str, str]]:
        """List all available serial ports.

        Returns:
            List of port information dictionaries
        """
        try:
            ports = serial.tools.list_ports.comports()
            port_list = []
            for port in ports:
                port_list.append(
                    {
                        "device": port.device,
                        "description": port.description,
                        "hwid": port.hwid if hasattr(port, "hwid") else "Unknown",
                    }
                )
            self.logger.info(f"Found {len(port_list)} serial ports")
            return port_list
        except Exception as e:
            self.logger.error(f"Error listing serial ports: {e}")
            return []

    async def connect(self, port: str, baudrate: int = 115200) -> Optional[MeshCore]:
        """Connect to a MeshCore device via serial port.

        Args:
            port: Serial port path
            baudrate: Connection baudrate

        Returns:
            MeshCore instance if successful, None otherwise
        """
        try:
            self.logger.info(f"Connecting to serial device: {port} at {baudrate} baud")
            meshcore = await MeshCore.create_serial(
                port=port, baudrate=baudrate, debug=False, only_error=False
            )

            # Test connection
            result = await meshcore.commands.send_device_query()
            if result.type == EventType.ERROR:
                self.logger.error(f"Device query failed: {result}")
                await meshcore.disconnect()
                return None

            self.logger.info(f"Connected to serial device: {port}")
            return meshcore

        except Exception as e:
            self.logger.error(f"Serial connection failed: {e}")
            return None


class BLETransport:
    """Handles BLE connections to MeshCore devices."""

    def __init__(self, config_dir: Path):
        self.logger = logging.getLogger("meshtui.transport.ble")
        self.config_dir = config_dir
        self.address_file = config_dir / "default_address"

    async def scan_devices(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """Scan for available BLE MeshCore devices.

        Args:
            timeout: Scan timeout in seconds

        Returns:
            List of discovered device information
        """
        try:
            self.logger.info(f"Scanning for BLE devices (timeout: {timeout}s)...")
            devices = await BleakScanner.discover(timeout=timeout)

            meshcore_devices = []
            for device in devices:
                if device.name and "meshcore" in device.name.lower():
                    meshcore_devices.append(
                        {
                            "name": device.name,
                            "address": device.address,
                            "rssi": getattr(device, "rssi", "Unknown"),
                        }
                    )

            self.logger.info(f"Found {len(meshcore_devices)} MeshCore BLE devices")
            return meshcore_devices

        except Exception as e:
            self.logger.error(f"BLE scan failed: {e}")
            return []

    def get_saved_address(self) -> Optional[str]:
        """Get the last used BLE address from config file.

        Returns:
            Saved BLE address or None
        """
        try:
            if self.address_file.exists():
                with open(self.address_file, "r", encoding="utf-8") as f:
                    address = f.read().strip()
                    self.logger.debug(f"Found saved BLE address: {address}")
                    return address
        except Exception as e:
            self.logger.debug(f"Could not read saved address: {e}")
        return None

    def save_address(self, address: str) -> None:
        """Save BLE address to config file.

        Args:
            address: BLE address to save
        """
        try:
            with open(self.address_file, "w", encoding="utf-8") as f:
                f.write(address)
            self.logger.debug(f"Saved BLE address: {address}")
        except Exception as e:
            self.logger.error(f"Could not save address: {e}")

    async def connect(
        self, address: Optional[str] = None, pin: Optional[str] = None
    ) -> Optional[MeshCore]:
        """Connect to a MeshCore device via BLE.

        Args:
            address: BLE address (if None, uses saved or scans)
            pin: Optional PIN for pairing

        Returns:
            MeshCore instance if successful, None otherwise
        """
        try:
            # Use saved address if none provided
            if not address:
                address = self.get_saved_address()

            # Scan if still no address
            if not address:
                self.logger.info("No address provided, scanning...")
                devices = await self.scan_devices()
                if devices:
                    address = devices[0]["address"]
                    self.logger.info(f"Using first discovered device: {address}")
                else:
                    self.logger.error("No MeshCore BLE devices found")
                    return None

            self.logger.info(f"Connecting to BLE device: {address}")
            if pin:
                meshcore = await MeshCore.create_ble(address=address, pin=pin)
            else:
                meshcore = await MeshCore.create_ble(address=address)

            # Test connection
            result = await meshcore.commands.send_device_query()
            if result.type == EventType.ERROR:
                self.logger.error(f"Device query failed: {result}")
                await meshcore.disconnect()
                return None

            # Save address for future use
            self.save_address(address)

            self.logger.info(f"Connected to BLE device: {address}")
            return meshcore

        except Exception as e:
            self.logger.error(f"BLE connection failed: {e}")
            return None


class TCPTransport:
    """Handles TCP/IP connections to MeshCore devices."""

    def __init__(self):
        self.logger = logging.getLogger("meshtui.transport.tcp")

    async def connect(self, hostname: str, port: int = 5000) -> Optional[MeshCore]:
        """Connect to a MeshCore device via TCP.

        Args:
            hostname: Hostname or IP address
            port: TCP port number

        Returns:
            MeshCore instance if successful, None otherwise
        """
        try:
            self.logger.info(f"Connecting to TCP device: {hostname}:{port}")
            meshcore = await MeshCore.create_tcp(
                host=hostname, port=port, debug=False, only_error=False
            )

            # Test connection
            result = await meshcore.commands.send_device_query()
            if result.type == EventType.ERROR:
                self.logger.error(f"Device query failed: {result}")
                await meshcore.disconnect()
                return None

            self.logger.info(f"Connected to TCP device: {hostname}:{port}")
            return meshcore

        except Exception as e:
            self.logger.error(f"TCP connection failed: {e}")
            return None
