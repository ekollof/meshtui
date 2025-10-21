# CLAUDE.md - MeshTUI Project Guide for AI Assistants

**Last Updated**: 2025-10-21

## Project Overview

**MeshTUI** is a full-featured MeshCore client with a comprehensive Terminal User Interface (TUI). Built with the Textual framework, it provides a complete mesh networking experience with keyboard-driven interface for managing mesh networks, sending messages, configuring devices, monitoring network status, and administering mesh nodes (repeaters, room servers, sensors).

### Quick Facts
- **Language**: Python 3.10+
- **UI Framework**: Textual (Terminal UI)
- **Hardware API**: meshcore Python library
- **Codebase Size**: ~5,200 lines of Python (including TCP proxy)
- **Architecture**: Layered, event-driven, async/await throughout
- **Entry Points**: `meshtui` CLI command, `meshcore-tcp-proxy` (optional)
- **Config Location**: `~/.config/meshtui/`

---

## Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│         UI Layer (app.py) - Textual Widgets             │
│         - Chat interface, contacts, logs, tabs          │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│     Connection Orchestration (connection.py)            │
│     - Lifecycle management, event handling              │
├─────────────┬──────────────┬──────────────┬─────────────┤
│ ContactMgr  │  ChannelMgr  │   RoomMgr    │  Database   │
│ contact.py  │  channel.py  │   room.py    │  database.py│
└─────────────┴──────────────┴──────────────┴─────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│       Transport Layer (transport.py)                    │
│       SerialTransport | BLETransport | TCPTransport     │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│       MeshCore Library (external dependency)            │
│       Low-level radio communication                     │
└─────────────────────────────────────────────────────────┘
```

### Key Principles
1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Async/Await Throughout**: All I/O operations are non-blocking
3. **Manager Pattern**: Domain logic delegated to specialized managers
4. **Event-Driven**: Reactive architecture using callbacks and event subscriptions
5. **Persistent Storage**: SQLite for message history and contact persistence

---

## Core Components

### 1. app.py (1,341 lines) - Main TUI Application
**Purpose**: Textual UI composition, user interactions, chat interface, node management

**Key Classes**:
- `MeshTUIApp` - Main Textual application class
- `ChatTab` - Chat interface widget
- `NodeManagementTab` - Node administration interface
- `ContactList` - Contact list widget with selection
- `Log` widget - Integrated logging display in Logs tab

**Important Methods**:
- `on_mount()` - Initialize widgets and start connection
- `on_button_pressed()` - Handle button clicks
- `handle_contact_selected()` - Switch active chat
- `handle_send_message()` - Send messages to contacts/channels

**UI Layout**: Two-panel design with sidebar (contacts/channels) and tabbed main content (Chat / Device Settings / Node Management / Logs)

### 2. connection.py (1,322 lines) - Connection Orchestration
**Purpose**: Device connection lifecycle, event handling, manager coordination

**Key Class**: `MeshConnection`

**Critical Methods**:
- `connect_serial()`, `connect_ble()`, `connect_tcp()` - Establish connections
- `_initialize_device_database()` - Initialize per-device database using device public key
- `_setup_event_handlers()` - Subscribe to meshcore events
- `_handle_contact_message()` - Process incoming messages (including room messages)
- `_handle_channel_message()` - Process channel messages
- `send_message()` - Send message to contact/channel
- `get_contacts()` - Retrieve contact list
- `get_channels()` - Retrieve channel list
- `has_gps()` - Detect if connected device has GPS available
- `auto_sync_time_if_needed()` - Automatically sync time for devices without GPS

**Event Handling**: Subscribes to meshcore events and updates managers/database

**Database Initialization**: Database is created per-device after connection, using the device's public key from `meshcore.self_info`

**Auto Time Sync**: On connection, automatically syncs device time if GPS is not detected (GPS-enabled devices get accurate time from satellites)

### 3. transport.py (269 lines) - Transport Layer
**Purpose**: Abstract BLE/Serial/TCP connectivity

**Key Classes**:
- `SerialTransport` - Serial port connections
- `BLETransport` - Bluetooth Low Energy
- `TCPTransport` - TCP/IP network connections

**Auto-detection**: Scans for devices, tests identification, prioritizes `/dev/ttyUSB0`

### 4. contact.py (204 lines) - Contact Manager
**Purpose**: Contact list operations, direct messaging

**Key Class**: `ContactManager`

**Features**:
- Contact type detection (Companion, Repeater, Room Server, Sensor)
- Direct message sending
- Contact filtering

### 5. channel.py (160 lines) - Channel Manager
**Purpose**: Channel discovery and messaging

**Key Class**: `ChannelManager`

**Features**:
- Channel discovery
- Channel message sending
- Join operations

### 6. room.py (274 lines) - Room Server Manager
**Purpose**: Room server authentication and administration

**Key Class**: `RoomManager`

**Features**:
- Room authentication with password
- Admin status tracking
- Login/logout operations

### 7. database.py (688 lines) - SQLite Persistence
**Purpose**: Message storage, contact persistence, unread tracking

**Key Class**: `MessageDatabase`

### 8. proxy/ (~860 lines) - TCP Proxy (EXPERIMENTAL)
**Purpose**: Expose Serial/BLE devices over TCP for remote access

**Status**: Phase 1 MVP complete, experimental

**Key Components**:
- `proxy.py` - Main orchestration (155 lines)
- `backends/serial.py` - Serial backend (190 lines)
- `tcp_server.py` - Multi-client TCP server (200 lines)
- `config.py` - Configuration system (156 lines)
- `__main__.py` - CLI entry point (159 lines)

**Features**:
- Zero protocol translation (identical 0x3C framing)
- Multi-client support
- YAML configuration
- CLI: `meshcore-tcp-proxy --serial /dev/ttyUSB0`

**Installation**: `pip install meshtui[proxy]`

**See**: `docs/MESHCORE_TCP_PROXY_DESIGN.md` for complete design

**Per-Device Databases**:
- Each connected device gets its own database file
- Database path: `~/.config/meshtui/devices/{device_pubkey[:16]}.db`
- Initialized after connection when device public key is available
- Prevents data collision when switching between devices

**Schema**:
- `messages` - Message history (sender, recipient, text, timestamp, channel)
- `contacts` - Contact persistence (pubkey, name, type, metadata)
- `last_read` - Unread message tracking

**Methods**:
- `store_message()` - Save message to history
- `get_messages_for_contact()` - Retrieve conversation history (including room messages from all users)
- `mark_as_read()` - Update read status
- `store_contact()` - Save contact to database

---

## Development Workflow

### Environment Setup
```bash
git clone <repo>
cd meshtui
python -m venv .venv       # Create virtual environment (or: uv venv)
source .venv/bin/activate  # Activate (Linux/Mac)
pip install -e .           # Install in development mode (or: uv pip install -e .)
```

**For end users**, install via `pipx` or `uv tool install`:
```bash
pipx install meshtui       # Recommended: isolates dependencies
# or
uv tool install meshtui    # Alternative with uv
```

### Running the Application
```bash
python -m meshtui                           # Basic launch
python -m meshtui --serial /dev/ttyUSB0     # With serial device
python -m meshtui --tcp 192.168.1.100:5000  # TCP connection
meshtui --address C2:2B:A1:D5:3E:B6          # BLE connection
```

### Testing
- **test_connection.py** - Comprehensive connection testing script
- **test_quick.py** - Quick integration test for basic connectivity
- **Manual Testing**: Requires physical MeshCore hardware

### Logging
- **File**: `~/.config/meshtui/meshtui.log`
- **Level**: DEBUG
- **Rotation**: 5MB per file, keeps 3 backups
- **View**: Integrated Logs tab in TUI + file output

---

## Code Style and Best Practices

### Python Standards (from .github/copilot-instructions.md)
1. **Type hints on all functions**
2. **Comprehensive docstrings**
3. **Try-catch blocks with logging for async operations**
4. **Structured logging** (DEBUG, INFO, ERROR levels)

### MeshCore API Patterns
1. **Connection status checks** before operations
2. **Command execution** through `commands` attribute:
   ```python
   device.commands.messaging.send_direct_message(recipient, text)
   ```
3. **Event subscription** for reactive updates:
   ```python
   device.subscribe(event_type, callback)
   ```
4. **Timeouts on all async operations**

### Textual UI Patterns
1. **Widget references** stored in `on_mount()`:
   ```python
   def on_mount(self):
       self.chat_display = self.query_one("#chat_display", Static)
   ```
2. **Event handlers** using `@on` decorator:
   ```python
   @on(Button.Pressed, "#send_button")
   def handle_send(self):
       ...
   ```
3. **UI updates from main thread**

### Git Operations
- **Use GitKraken tools** (not raw git commands)
- **Prefer** `mcp_gitkraken_*` functions

---

## Common Tasks and Patterns

### Adding a New Feature
1. Identify the appropriate layer (UI, Connection, Manager, Transport)
2. Update the relevant manager if domain logic is needed
3. Add event handlers in `connection.py` if events are involved
4. Update UI in `app.py` for user interaction
5. Add persistence in `database.py` if data needs to be saved
6. Update tests in `test_connection.py`

### Adding a New Contact Type
1. Update `ContactType` enum in `contact.py`
2. Add detection logic in `ContactManager._detect_contact_type()`
3. Update UI rendering in `app.py` if special display is needed
4. Update database schema if new metadata is required

### Adding Event Handling
1. Identify the event type from meshcore API
2. Subscribe in `connection.py` `_setup_event_handlers()`
3. Add handler method `_handle_<event_name>()`
4. Update relevant manager (ContactManager, ChannelManager, etc.)
5. Update UI via callback to `app.py`

### Debugging Connection Issues
1. Check `~/.config/meshtui/meshtui.log` for DEBUG logs
2. Verify device identification in transport layer
3. Check event subscription success in connection layer
4. Verify meshcore API compatibility
5. Test with `test_connection.py` script

---

## Important File Locations

### Source Code
- **Main entry**: `src/meshtui/__main__.py`
- **UI layer**: `src/meshtui/app.py`, `src/meshtui/app.css`
- **Connection**: `src/meshtui/connection.py`
- **Transports**: `src/meshtui/transport.py`
- **Managers**: `src/meshtui/{contact,channel,room}.py`
- **Database**: `src/meshtui/database.py`

### Configuration and Data
- **Config dir**: `~/.config/meshtui/`
- **Log file**: `~/.config/meshtui/meshtui.log`
- **Databases**:
  - Per-device: `~/.config/meshtui/devices/{pubkey}.db` (one per device)
  - Legacy: `~/.config/meshtui/meshtui.db` (deprecated, for backward compatibility)
- **Saved BLE address**: `~/.config/meshtui/default_address`

### Documentation
- **README**: Project overview and usage
- **CHANGES.md**: Changelog and architecture notes
- **CHAT_USAGE.md**: Chat feature usage guide
- **FIXED_ISSUES.md**: Issue resolution summary
- **docs/meshcore-api/**: MeshCore API reference

### Configuration Files
- **pyproject.toml**: Project metadata, dependencies, build config
- **package.json**: Node.js package config (for Claude Code)
- **.github/copilot-instructions.md**: Development guidelines

---

## Dependencies

### Core
- **meshcore** >= 2.1.9 - MeshCore radio communication library
- **textual** >= 0.50.0 - Terminal UI framework
- **requests** >= 2.28.0 - HTTP client
- **aiohttp** >= 3.9.0 - Async HTTP client

### Included with meshcore
- **pyserial** - Serial port connectivity
- **bleak** - Bluetooth Low Energy communication

### Standard Library
- **sqlite3** - Database
- **asyncio** - Async I/O
- **logging** - Structured logging

---

## Known Issues and Quirks

### EventDispatcher Task Warnings
**Symptom**: `Task was destroyed but it is pending!` warnings from meshcore
**Cause**: Upstream meshcore library issue
**Impact**: Harmless, doesn't affect functionality
**Status**: No action required

### Empty Contacts on Fresh Device
**Symptom**: No contacts appear in contact list
**Cause**: Fresh device or single-device setup
**Solution**: Normal behavior - contacts populate after mesh communication

### Serial Port Permissions
**Symptom**: Connection fails with "Permission denied" or "Could not open port" errors
**Cause**: User not in `dialout` group (Linux) or insufficient permissions
**Solution**:
- **Linux**: `sudo usermod -a -G dialout $USER` then logout/login (or use `newgrp dialout`)
- **macOS**: Usually no special permissions needed, check device ownership with `ls -l /dev/tty.*`
- **Verify**: Run `groups` to confirm group membership, or `ls -l /dev/ttyUSB0` to check device permissions
**Impact**: Cannot connect to serial devices until permissions are fixed

### BLE Scanning Requires Bluetooth Hardware
**Symptom**: BLE scan fails
**Cause**: No Bluetooth adapter or disabled Bluetooth
**Solution**: Enable Bluetooth or use Serial/TCP connection

---

## API Reference Shortcuts

### MeshCore Commands (via `device.commands`)
```python
# Messaging
device.commands.messaging.send_direct_message(recipient_id, text)
device.commands.messaging.send_channel_message(channel, text)

# Contacts
device.commands.contacts.get_contacts()
device.commands.contacts.add_contact(name, pubkey)

# Device
device.commands.device.get_info()
device.commands.device.get_status()

# Channels
device.commands.channels.get_channels()
device.commands.channels.join_channel(channel_name)

# Node Management
device.commands.room.login(node_name, password)
device.commands.room.send_command(command_text)
device.commands.room.logout()
```

### Event Types (subscription)
- `"contact_added"` - New contact detected
- `"contact_updated"` - Contact info changed
- `"message_received"` - Incoming message
- `"channel_message"` - Channel message
- `"device_status"` - Device telemetry update
- `"node_discovered"` - Remote node found

---

## Recent Development History

**Latest Changes**:
1. **TCP Proxy (EXPERIMENTAL)** - Phase 1 MVP complete: expose Serial devices over TCP (~860 lines)
2. **Auto Time Sync** - Automatically syncs device time on connection for devices without GPS
3. **GPS Detection** - Added GPS availability detection via telemetry mode
4. **Per-Device Databases** - Each device now gets its own database file to prevent data collision
5. **Room Messaging Fix** - Fixed room messages from other users not appearing in real-time
6. **Device Settings UI** - Added comprehensive device configuration tab
7. **Improved Autodetection** - Enhanced serial device identification reliability

**Recent Focus Areas**:
- TCP proxy for remote device access (experimental)
- Automatic time synchronization for non-GPS devices
- GPS capability detection
- Per-device data isolation
- Room server messaging improvements
- Device configuration management
- Test coverage and reliability
- Connection stability

---

## Testing Checklist

When making changes, verify:

### Connection Layer
- [ ] Serial device detection works
- [ ] BLE device scanning works
- [ ] Device identification succeeds
- [ ] Event subscriptions are established
- [ ] Reconnection logic functions

### UI Layer
- [ ] Widgets render correctly
- [ ] User input is handled
- [ ] Logs tab displays output
- [ ] Tabs switch properly
- [ ] Contact selection works

### Managers
- [ ] ContactManager populates list
- [ ] ChannelManager discovers channels
- [ ] RoomManager authenticates
- [ ] Database persistence works

### Integration
- [ ] Messages send successfully
- [ ] Events update UI
- [ ] Log file is written
- [ ] Config is saved
- [ ] Application exits cleanly

---

## Useful Commands for Development

### Git (via GitKraken)
Use GitKraken tools for all git operations (per project guidelines)

### Package Management
```bash
pip install -e .             # Install in dev mode (or: uv pip install -e .)
pip list                     # List installed packages (or: uv pip list)
pip install <package>        # Add dependency (or: uv pip install <package>)
```

**End user installation**:
```bash
pipx install meshtui         # Recommended: isolated environment
pipx upgrade meshtui         # Upgrade to latest version
pipx uninstall meshtui       # Uninstall
```

### Testing
```bash
python test_connection.py    # Run connection tests
python test_quick.py         # Quick integration test
python -m meshtui            # Run application
```

### Debugging
```bash
tail -f ~/.config/meshtui/meshtui.log  # Watch logs in real-time
sqlite3 ~/.config/meshtui/devices/*.db # Inspect device databases
ls -la /dev/ttyUSB* /dev/ttyACM*       # Check serial devices and permissions
groups                                  # Check if user is in dialout group
bluetoothctl                            # Check BLE devices
```

---

## Questions to Ask Before Making Changes

1. **Which layer does this change belong to?** (UI, Connection, Manager, Transport)
2. **Does this require event handling?** (Add subscription in connection.py)
3. **Does this need persistence?** (Update database.py schema)
4. **Does this affect the UI?** (Update app.py widgets and handlers)
5. **Is this async?** (Use async/await, add timeouts, handle errors)
6. **Does this need testing?** (Update test_connection.py)
7. **Does this change the API?** (Update docs/meshcore-api/)

---

## Contact and Support

- **Issues**: Submit to project repository
- **Documentation**: See README.md and docs/meshcore-api/
- **MeshCore Library**: https://github.com/fdlamotte/meshcore_py
- **Textual Framework**: https://textual.textualize.io/

---

## Summary for AI Assistants

MeshTUI is a well-architected Python TUI for mesh network communication. When working on this codebase:

1. **Respect the layers** - don't bypass abstraction boundaries
2. **Use async/await** - all I/O is non-blocking
3. **Log everything** - use structured logging at appropriate levels
4. **Follow event patterns** - subscribe to events, don't poll
5. **Persist important data** - use database for messages and contacts
6. **Update UI reactively** - respond to events, don't update speculatively
7. **Test with hardware** - changes often require physical MeshCore devices
8. **Check logs first** - most issues are visible in `~/.config/meshtui/meshtui.log`

The codebase is mature, well-documented, and follows Python best practices. Most common tasks involve adding event handlers, updating managers, or enhancing the UI - all of which have clear patterns to follow.
