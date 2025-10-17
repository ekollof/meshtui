#!/usr/bin/env python3
"""Quick test to verify connection and contacts without full TUI."""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from meshtui.connection import MeshConnection

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def test():
    conn = MeshConnection()
    print("\n=== Testing MeshCore Connection ===\n")
    
    # Try connecting to /dev/ttyUSB0
    print("Connecting to /dev/ttyUSB0...")
    success = await conn.connect_serial("/dev/ttyUSB0")
    
    if not success:
        print("❌ Connection failed")
        return
    
    print("✅ Connected successfully!")
    print(f"Device info: {conn.get_device_info()}")
    
    # Wait a bit for events to fire
    print("\nWaiting 2 seconds for contact events...")
    await asyncio.sleep(2)
    
    # Check contacts
    contacts = conn.get_contacts()
    print(f"\n📇 Contacts: {len(contacts)} found")
    for c in contacts:
        print(f"  - {c.get('name', 'Unknown')}")
        print(f"    Raw data: {c}")
    
    # Check channels
    channels = await conn.get_channels()
    print(f"\n📻 Channels: {len(channels)} found")
    for ch in channels:
        print(f"  - {ch.get('name', 'Unknown')}")
    
    print("\n=== Test Complete ===")
    await conn.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
