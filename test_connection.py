#!/usr/bin/env python3
"""
Test script for MeshConnection functionality.
Tests the improved autodetection, retry logic, and all meshtui internals.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the src directory to the path so we can import meshtui
sys.path.insert(0, str(Path(__file__).parent / "src"))

from meshtui.connection import MeshConnection
from meshtui.transport import SerialTransport


# Filter for asyncio to suppress known harmless EventDispatcher warnings
class EventDispatcherFilter(logging.Filter):
    """Filter out known harmless EventDispatcher task warnings from meshcore library.

    These warnings occur when temporary MeshCore connections are created during
    device identification. The tasks are cleaned up properly, but asyncio logs
    warnings about them. This is a known upstream issue in the meshcore library
    and doesn't affect functionality.

    See CLAUDE.md "Known Issues and Quirks" section for details.
    """
    def filter(self, record):
        # Suppress "Task was destroyed but it is pending" messages about EventDispatcher
        if "Task was destroyed but it is pending" in record.getMessage():
            if "EventDispatcher._process_events" in record.getMessage():
                return False
        return True


async def test_autodetection():
    """Test the improved autodetection features."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")

    # Create connection instance
    conn = MeshConnection()
    logger.info("=== Testing Improved Autodetection ===")

    try:
        # Test 1: Quick scan mode (new feature)
        logger.info("\n--- Test 1: Quick Scan (USB devices only, stops at first match) ---")
        serial_devices = await conn.scan_serial_devices(quick_scan=True)

        if serial_devices:
            logger.info(f"Quick scan found {len(serial_devices)} device(s):")
            for device in serial_devices:
                is_meshcore = "✓ MeshCore" if device.get("is_meshcore") else "✗ Not MeshCore"
                logger.info(f"  {is_meshcore}: {device['device']} - {device['description']}")
        else:
            logger.info("Quick scan: No serial devices found")

        # Test 2: Full scan mode (existing behavior with improvements)
        logger.info("\n--- Test 2: Full Scan (all devices with USB prioritization) ---")
        all_devices = await conn.scan_serial_devices(quick_scan=False)

        if all_devices:
            logger.info(f"Full scan found {len(all_devices)} device(s):")
            meshcore_count = 0
            for device in all_devices:
                is_meshcore = device.get("is_meshcore", False)
                if is_meshcore:
                    meshcore_count += 1
                status = "✓ MeshCore" if is_meshcore else "✗ Not MeshCore"
                logger.info(f"  {status}: {device['device']} - {device['description']}")
            logger.info(f"Found {meshcore_count} MeshCore device(s)")
        else:
            logger.info("Full scan: No serial devices found")

        # Test 3: Test SerialTransport.identify_device() with retry logic
        logger.info("\n--- Test 3: Device Identification with Retry Logic ---")
        if all_devices:
            test_device = all_devices[0]['device']
            logger.info(f"Testing identification on {test_device} (with 2 retries)...")
            transport = SerialTransport()
            is_meshcore = await transport.identify_device(test_device, timeout=5.0, retries=2)
            if is_meshcore:
                logger.info(f"✓ {test_device} identified as MeshCore device")
            else:
                logger.info(f"✗ {test_device} is not a MeshCore device")

        # Test 4: BLE scanning
        logger.info("\n--- Test 4: BLE Device Scanning ---")
        ble_devices = await conn.scan_ble_devices(timeout=3.0)

        if ble_devices:
            logger.info(f"Found {len(ble_devices)} MeshCore BLE device(s):")
            for device in ble_devices:
                logger.info(
                    f"  - {device['name']} ({device['address']}) RSSI: {device['rssi']}"
                )
        else:
            logger.info("No MeshCore BLE devices found")

        return serial_devices, ble_devices

    except Exception as e:
        logger.error(f"Autodetection tests failed: {e}")
        import traceback
        traceback.print_exc()
        return [], []


async def test_connection():
    """Test the MeshConnection functionality."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")

    # Create connection instance
    conn = MeshConnection()
    logger.info("Created MeshConnection instance")

    try:
        # Run autodetection tests first
        serial_devices, devices = await test_autodetection()

        # Test 5: Connection tests
        logger.info("\n=== Testing Connection Features ===")

        # Find a MeshCore device to test with
        meshcore_device = next(
            (d for d in serial_devices if d.get("is_meshcore", False)), None
        )

        if meshcore_device:
            device_path = meshcore_device["device"]
            logger.info(f"\n--- Test 5: Connect to MeshCore device at {device_path} ---")

            # Test with verify_meshcore=False for faster connection (user-specified device)
            logger.info("Testing connection with verify_meshcore=False (faster)...")
            success = await conn.connect_serial(port=device_path, verify_meshcore=False)

            if success:
                logger.info("✓ Serial connection successful!")
                device_info = conn.get_device_info()
                logger.info(f"Device info: {device_info}")

                # Test 6: Contact management
                logger.info("\n--- Test 6: Contact Management ---")
                await conn.refresh_contacts()
                contacts = conn.get_contacts()
                logger.info(f"Found {len(contacts)} contacts")
                for contact in contacts[:5]:  # Show first 5
                    name = contact.get('name') or contact.get('adv_name', 'Unknown')
                    contact_type = contact.get('type', 'Unknown')
                    logger.info(f"  - {name} (type: {contact_type})")

                # Test 7: Channel management
                logger.info("\n--- Test 7: Channel Management ---")
                channels = await conn.get_channels()
                logger.info(f"Found {len(channels)} channels")
                for channel in channels:
                    logger.info(f"  - {channel.get('name', 'Unknown')}")

                # Test 8: Node management functionality
                logger.info("\n--- Test 8: Node Management (Repeaters/Room Servers) ---")

                # Test getting available nodes
                nodes = await conn.get_available_nodes()
                logger.info(f"Found {len(nodes)} available nodes")

                # Test room server detection
                if conn.contacts:
                    room_servers = [c for c in conn.contacts.get_all() if conn.contacts.is_room_server(c)]
                    repeaters = [c for c in conn.contacts.get_all() if conn.contacts.is_repeater(c)]
                    logger.info(f"  Room servers: {len(room_servers)}")
                    logger.info(f"  Repeaters: {len(repeaters)}")

                # Test repeater/room login (if nodes exist)
                if nodes:
                    test_node = nodes[0]["name"]
                    logger.info(f"\n--- Test 9: Login to node: {test_node} ---")
                    logger.info("Note: This will fail without proper password - testing logic only")

                    # Determine if it's a room server or repeater
                    node_contact = conn.contacts.get_by_name(test_node) if conn.contacts else None
                    if node_contact:
                        is_room = conn.contacts.is_room_server(node_contact)
                        node_type = "room server" if is_room else "repeater"
                        logger.info(f"Node type: {node_type}")

                    # Try login (will likely fail without proper credentials)
                    if node_contact and conn.contacts.is_room_server(node_contact):
                        login_success = await conn.login_to_room(test_node, "test_password")
                    else:
                        login_success = await conn.login_to_repeater(test_node, "test_password")

                    if login_success:
                        logger.info(f"✓ Login to {test_node} successful")

                        # Test sending command
                        logger.info("Testing command send...")
                        cmd_success = await conn.send_command_to_repeater(test_node, "status")
                        if cmd_success:
                            logger.info(f"✓ Command sent to {test_node}")

                        # Test getting status
                        logger.info("Testing status request...")
                        status = await conn.request_repeater_status(test_node)
                        if status:
                            logger.info(f"Status from {test_node}: {status}")

                        # Test logout
                        logout_success = await conn.logout_from_repeater(test_node)
                        if logout_success:
                            logger.info(f"✓ Logout from {test_node} successful")
                    else:
                        logger.info(f"✗ Login to {test_node} failed (expected without proper credentials)")

                # Test 10: Disconnect
                logger.info("\n--- Test 10: Disconnect ---")
                await conn.disconnect()
                logger.info("✓ Disconnected successfully")
            else:
                logger.info("✗ Serial connection failed")

        # Fallback to BLE if no serial MeshCore device found
        elif devices:
            logger.info("\n--- No MeshCore serial device found, trying BLE ---")
            logger.info(f"Attempting to connect to first BLE device: {devices[0]['name']}...")
            success = await conn.connect_ble(
                address=devices[0]["address"], device=devices[0]["device"]
            )

            if success:
                logger.info("✓ BLE connection successful!")
                device_info = conn.get_device_info()
                logger.info(f"Device info: {device_info}")

                # Test getting contacts
                await conn.refresh_contacts()
                contacts = conn.get_contacts()
                logger.info(f"Found {len(contacts)} contacts")

                # Disconnect
                await conn.disconnect()
                logger.info("✓ Disconnected")
            else:
                logger.info("✗ BLE connection failed")
        else:
            logger.info("\n⚠ No MeshCore devices found - skipping connection tests")
            logger.info("This is expected if no MeshCore hardware is connected")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main entry point."""
    # Apply filter to suppress known harmless asyncio warnings
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.addFilter(EventDispatcherFilter())

    print("\n" + "=" * 70)
    print("MeshTUI Connection & Autodetection Test Suite")
    print("=" * 70)
    print("\nThis test suite validates:")
    print("  ✓ Improved serial device autodetection with retry logic")
    print("  ✓ Quick scan mode (USB devices, stops at first match)")
    print("  ✓ Full scan mode (all devices with USB prioritization)")
    print("  ✓ Device identification with configurable retries")
    print("  ✓ Connection management (serial & BLE)")
    print("  ✓ Contact, channel, and node management")
    print("  ✓ Room server and repeater functionality")
    print("\n" + "=" * 70 + "\n")

    try:
        asyncio.run(test_connection())
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("Test suite completed")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
