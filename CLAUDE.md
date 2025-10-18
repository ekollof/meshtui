# CLAUDE.md - MeshTUI Project Guide for AI Assistants

**Last Updated**: 2025-10-18

## Project Overview

**MeshTUI** is a Terminal User Interface (TUI) client for interacting with MeshCore companion radios - mesh network communication devices. Built with the Textual framework, it provides a keyboard-driven interface for managing mesh networks, sending messages, monitoring device status, and administering mesh nodes.

### Quick Facts
- **Language**: Python 3.10+
- **UI Framework**: Textual (Terminal UI)
- **Hardware API**: meshcore Python library
- **Codebase Size**: ~4,300 lines of Python
- **Architecture**: Layered, event-driven, async/await throughout
- **Entry Point**: `meshtui` CLI command
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
- `LogPanel` - Integrated logging display

**Important Methods**:
- `on_mount()` - Initialize widgets and start connection
- `on_button_pressed()` - Handle button clicks
- `handle_contact_selected()` - Switch active chat
- `handle_send_message()` - Send messages to contacts/channels

**UI Layout**: Three-panel design with tabbed center panel (Chat / Node Management)

### 2. connection.py (1,322 lines) - Connection Orchestration
**Purpose**: Device connection lifecycle, event handling, manager coordination

**Key Class**: `MeshConnection`

**Critical Methods**:
- `connect()` - Establish connection (BLE/Serial/TCP)
- `_setup_event_handlers()` - Subscribe to meshcore events
- `_handle_event()` - Process incoming events from radio
- `send_message()` - Send message to contact/channel
- `get_contacts()` - Retrieve contact list
- `get_channels()` - Retrieve channel list

**Event Handling**: Subscribes to meshcore events and updates managers/database

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

**Key Class**: `Database`

**Schema**:
- `messages` - Message history (sender, recipient, text, timestamp, channel)
- `contacts` - Contact persistence (pubkey, name, type, metadata)
- `last_read` - Unread message tracking

**Methods**:
- `store_message()` - Save message to history
- `get_messages_with()` - Retrieve conversation history
- `mark_as_read()` - Update read status
- `persist_contact()` - Save contact to database

---

## Development Workflow

### Environment Setup
```bash
git clone <repo>
cd meshtui
uv venv                    # Create virtual environment
source .venv/bin/activate  # Activate (Linux/Mac)
uv pip install -e .        # Install in development mode
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
- **View**: Integrated log panel in TUI + file output

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
- **Database**: `~/.config/meshtui/meshtui.db`
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
**Symptom**: Connection fails on Linux
**Cause**: User not in `dialout` group
**Solution**: `sudo usermod -a -G dialout $USER` and logout/login

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

**Last 4 commits**:
1. **1f1691f** - Add Node Management tab with command interface and reference
2. **3c20166** - Checkpoint: Before pubkey-based refactor
3. **33164be** - Update copilot instructions to use GitKraken for git operations
4. **26f51c1** - Add SQLite database with persistent message storage and unread tracking

**Recent Focus Areas**:
- Node administration features
- Database persistence
- Event-driven architecture improvements
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
- [ ] Log panel displays output
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
uv pip install -e .          # Install in dev mode
uv pip list                  # List installed packages
uv pip install <package>     # Add dependency
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
sqlite3 ~/.config/meshtui/meshtui.db   # Inspect database
ls -la /dev/ttyUSB*          # Check serial devices
bluetoothctl                 # Check BLE devices
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
