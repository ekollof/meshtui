#!/usr/bin/env python3
"""
Test script for MeshConnection functionality.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the src directory to the path so we can import meshtui
sys.path.insert(0, str(Path(__file__).parent / "src"))

from meshtui.connection import MeshConnection


async def test_connection():
    """Test the MeshConnection functionality."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")

    # Create connection instance
    conn = MeshConnection()
    logger.info("Created MeshConnection instance")

    try:
        # Test serial scanning
        logger.info("Testing serial device scanning...")
        serial_devices = await conn.scan_serial_devices()

        if serial_devices:
            logger.info(f"Found {len(serial_devices)} serial devices:")
            for device in serial_devices:
                logger.info(f"  - {device['device']} ({device['description']})")
        else:
            logger.info("No serial devices found")

        # Test BLE scanning
        logger.info("Testing BLE device scanning...")
        devices = await conn.scan_ble_devices(timeout=3.0)

        if devices:
            logger.info(f"Found {len(devices)} MeshCore devices:")
            for device in devices:
                logger.info(
                    f"  - {device['name']} ({device['address']}) RSSI: {device['rssi']}"
                )
        else:
            logger.info("No MeshCore BLE devices found")

        # Test connection (will likely fail without hardware, but tests the logic)
        # First, try to connect to /dev/ttyUSB0 if available
        usb_device = next(
            (d for d in serial_devices if d["device"] == "/dev/ttyUSB0"), None
        )
        if usb_device:
            logger.info("Attempting to connect to /dev/ttyUSB0...")
            success = await conn.connect_serial(port="/dev/ttyUSB0")

            if success:
                logger.info("Serial connection successful!")
                device_info = conn.get_device_info()
                logger.info(f"Device info: {device_info}")

                # Test getting contacts
                await conn.refresh_contacts()
                contacts = conn.get_contacts()
                logger.info(f"Found {len(contacts)} contacts")

                # Test node management functionality
                logger.info("Testing node management functionality...")

                # Test getting available nodes
                nodes = await conn.get_available_nodes()
                logger.info(f"Found {len(nodes)} available nodes")

                # Test repeater login (if nodes exist)
                if nodes:
                    test_node = nodes[0]["name"]
                    logger.info(f"Testing login to node: {test_node}")
                    # Note: This will likely fail without proper setup
                    login_success = await conn.login_to_repeater(
                        test_node, "test_password"
                    )
                    if login_success:
                        logger.info(f"Login to {test_node} successful")

                        # Test sending command
                        cmd_success = await conn.send_command_to_repeater(
                            test_node, "status"
                        )
                        if cmd_success:
                            logger.info(f"Command sent to {test_node}")

                        # Test getting status
                        status = await conn.request_repeater_status(test_node)
                        if status:
                            logger.info(f"Status from {test_node}: {status}")

                        # Test logout
                        logout_success = await conn.logout_from_repeater(test_node)
                        if logout_success:
                            logger.info(f"Logout from {test_node} successful")
                    else:
                        logger.info(
                            f"Login to {test_node} failed (expected without proper setup)"
                        )

                # Disconnect
                await conn.disconnect()
                logger.info("Disconnected")
            else:
                logger.info("Serial connection failed (expected without hardware)")
        elif devices:
            logger.info("Attempting to connect to first BLE device...")
            success = await conn.connect_ble(
                address=devices[0]["address"], device=devices[0]["device"]
            )

            if success:
                logger.info("BLE connection successful!")
                device_info = conn.get_device_info()
                logger.info(f"Device info: {device_info}")

                # Test getting contacts
                await conn.refresh_contacts()
                contacts = conn.get_contacts()
                logger.info(f"Found {len(contacts)} contacts")

                # Disconnect
                await conn.disconnect()
                logger.info("Disconnected")
            else:
                logger.info("BLE connection failed (expected without hardware)")
        else:
            logger.info("Skipping connection test - no compatible devices found")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main entry point."""
    print("MeshTUI Connection Test")
    print("=" * 40)

    try:
        asyncio.run(test_connection())
    except KeyboardInterrupt:
        print("\nTest interrupted")
    except Exception as e:
        print(f"Test error: {e}")
        import traceback

        traceback.print_exc()

    print("Test completed")


if __name__ == "__main__":
    main()
