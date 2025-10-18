# MeshCore API Reference

This directory contains a copy of the MeshCore Python API for reference purposes.

## Key Files

### Core API
- `meshcore.py` - Main MeshCore class and connection management
- `events.py` - Event types and event handling
- `reader.py` - Protocol reader and message parsing
- `packets.py` - Packet definitions

### Connection Types
- `ble_cx.py` - Bluetooth LE connection
- `serial_cx.py` - Serial port connection  
- `tcp_cx.py` - TCP/IP connection
- `connection_manager.py` - Connection lifecycle management

### Command Modules (`commands/`)
- `base.py` - Base command handler
- `messaging.py` - Send messages, advertisements
- `contact.py` - Contact management
- `device.py` - Device configuration and status
- `binary.py` - Binary data handling

## Important APIs

### Messaging Commands
```python
# Send direct message to contact
await mc.commands.send_msg(contact_or_pubkey, message_text)

# Send channel message
await mc.commands.send_chan_msg(channel_index, message_text)

# Send command to room/repeater/sensor (type 2, 3, or 4)
await mc.commands.send_cmd(contact_or_pubkey, command_text)

# Send advertisement
await mc.commands.send_advert(flood=True)  # flood=True for 3 hops, False for 0 hops
```

### Contact Management
```python
# Get contacts
await mc.commands.get_contacts()

# Get contact by name
contact = mc.get_contact_by_name(name)

# Get contact by key prefix
contact = mc.get_contact_by_key_prefix(pubkey_prefix)
```

### Room Server Operations
```python
# Login to room (type 3 contact)
await mc.commands.login(room_name_or_contact, password)

# Logout from room
await mc.commands.logout(room_name_or_contact)

# Get queued messages from room
await mc.commands.get_msg()
```

### Device Configuration
```python
# Get device info
await mc.commands.send_device_query()

# Reboot device
await mc.commands.reboot()

# Get channel info
await mc.commands.get_channel(channel_index)

# Set channel
await mc.commands.set_channel(channel_index, channel_name, channel_secret_bytes)
```

## Contact Types
- `0` = Public channel
- `1` = Companion node (regular contact)
- `2` = Repeater node
- `3` = Room server (requires password authentication)
- `4` = Sensor node

## Event Types
All events are defined in `events.py`:
- `CONTACT_MSG_RECV` - Direct message received
- `CHANNEL_MSG_RECV` - Channel message received
- `NEW_CONTACT` - New contact discovered
- `CONTACTS_UPDATE` - Contacts list updated
- `ADVERTISEMENT` - Advertisement received
- `PATH_UPDATE` - Routing path updated
- `CHANNEL_INFO` - Channel information
- `ERROR` - Error occurred
- `NO_MORE_MSGS` - No more queued messages (from room server)

## Usage Pattern
```python
from meshcore import MeshCore, EventType

# Create instance
mc = MeshCore()

# Subscribe to events
mc.subscribe(EventType.CONTACT_MSG_RECV, handle_message)

# Connect (serial/BLE/TCP)
await mc.connect_serial(port="/dev/ttyUSB0", baudrate=115200)

# Send commands
result = await mc.commands.send_msg(contact, "Hello!")

# Check result
if result.type == EventType.ERROR:
    print(f"Error: {result}")
else:
    print(f"Success: {result.payload}")
```

## Room Server Administration

Room servers (type 3 contacts) support remote administration via commands:

```python
# Must login first
await mc.commands.login(room_contact, password)

# Send administrative commands
await mc.commands.send_cmd(room_contact, "help")
await mc.commands.send_cmd(room_contact, "list_users")
await mc.commands.send_cmd(room_contact, "kick username")
# ... other admin commands

# Logout when done
await mc.commands.logout(room_contact)
```

## Notes

- Contact lookups should use public keys, not display names (names can be spoofed)
- Messages may contain short pubkey prefixes instead of full keys
- Always check `result.type != EventType.ERROR` before using `result.payload`
- Use timeouts for async operations: `await asyncio.wait_for(operation(), timeout=5.0)`
