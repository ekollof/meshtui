# MeshTUI Changelog

## Version 0.1.2 (2025-10-21)

### Contact Info Tab Auto-Hide for Channels
- **Feature**: Contact Info tab now automatically hides when a channel is selected
- **Behavior**: Tab shows only for contacts (where metadata like last seen, public keys, network paths are relevant)
- **Why**: Channels don't have contact-specific metadata, so the tab was unnecessary and confusing
- **Implementation**: Uses Textual's `hide_tab()` and `show_tab()` methods on TabbedContent widget

### Automatic Time Synchronization
- **Feature**: Automatically sync device clock on connection for devices without GPS
- **GPS Detection**: Smart detection of GPS availability via telemetry mode and coordinates
- **When It Runs**: Triggered automatically during serial, BLE, and TCP connections
- **Logic**: GPS-enabled devices get accurate time from satellites, so sync is skipped for those
- **Why It Matters**: Devices without GPS often have incorrect time, affecting message timestamps and network operations

### Technical Implementation
- Added `has_gps()` method to detect GPS availability
  - Checks location telemetry mode (`telemetry_mode_loc`)
  - Checks for non-zero coordinates (`adv_lat`, `adv_lon`)
- Added `auto_sync_time_if_needed()` method
  - Automatically called after successful connection
  - Uses system time via `time.time()`
  - Includes timeout handling and error logging
- Integration in all connection methods:
  - `connect_serial()` - Line 415
  - `connect_ble()` - Line 310
  - `connect_tcp()` - Line 354

### Module Changes
- `src/meshtui/connection.py` - GPS detection and auto time sync methods

## Version 0.1.1 (2025-10-20)

### Documentation Updates
- **Installation**: Updated documentation to prominently feature `pipx` as the recommended installation method
- **Development**: Added standard Python `venv` and `pip` workflow alongside `uv` alternatives
- **Accessibility**: Made project more accessible to developers who don't use `uv`
- **README.md**: Updated PyPI Installation, Development Installation, and Development sections
- **CLAUDE.md**: Updated Environment Setup and Package Management sections with `pipx` examples

### Why this update?
- `pipx` is the standard tool for installing Python CLI applications with proper dependency isolation
- Documentation now covers the full spectrum: end users (pipx), power users (uv tool), and developers (standard venv/pip or uv)

## Version 0.1.0 (2025-10-20)

### Channel Creation UI
- **Feature**: Create custom encrypted channels directly from the UI
- **UI Element**: "+" button next to Channels header
- **Auto-hash Support**: Use # prefix (e.g., #mychannel) for automatic secret generation
- **Channel Slots**: Support for channels 1-7 (0 is reserved for Public)
- **Modal Dialog**: User-friendly creation dialog with validation
- **Automatic Refresh**: Channels list updates immediately after creation

### F1 Help System
- **Feature**: Comprehensive in-app help accessible via F1 key
- **Content**: Navigation, messaging, delivery tracking, node management
- **Keyboard Shortcuts**: All available shortcuts documented
- **Channel Creation**: Step-by-step instructions included
- **Modal Screen**: Press any key to close

### Bug Fixes
- Fixed unread count incrementing for sent messages
- Fixed room messages appearing in direct contact conversations
- Fixed channel message filtering by channel slot
- Improved channel ID mapping for proper database queries
- Better error handling and validation in channel creation

### Technical Implementation
- Added `create_channel()` method to connection manager
- Added `refresh()` method to ChannelManager
- Channel selection now properly extracts channel index
- Database queries use "Channel X" format for consistency
- Mark messages as read immediately after sending

### Module Changes
- `src/meshtui/connection.py` - Channel creation, mark as read on send
- `src/meshtui/channel.py` - Channel refresh method
- `src/meshtui/database.py` - Fixed room message filtering
- `src/meshtui/app.py` - Channel creation UI, F1 help, improved channel handling
- `src/meshtui/app.css` - Styling for channel creation dialog

## Previous Updates (2025-10-20)

### Message Delivery Tracking and Retry Logic
- **Feature**: Comprehensive delivery tracking for direct messages
- **ACK Tracking**: Monitor repeater acknowledgments with "✓ Heard X repeats"
- **Timeout Detection**: Automatic failure detection with "✗ Delivery failed (no repeaters)"
- **Automatic Retry**: Messages retry up to 3 times with intelligent flood routing fallback
- **Database Tracking**: All delivery information stored for later analysis
  - `ack_code` - Unique acknowledgment code
  - `delivery_status` - 'sent', 'repeated', 'failed', or 'broadcast'
  - `repeat_count` - Number of repeater ACKs
  - `last_ack_time` - Timestamp of last ACK
- **UI Improvements**: Messages displayed immediately, status appears after
- **Channel Support**: Channel messages show "✓ Sent (broadcast)" (no ACK per API)

### Technical Implementation
- Added `_pending_acks` dictionary to track message ACKs
- Implemented `_handle_ack()` event handler for ACK events
- Added `_check_message_timeout()` for timeout-based failure detection
- Updated `ContactManager.send_message()` to use `send_msg_with_retry()`
- Modified database schema to include delivery tracking fields
- Added `update_message_delivery_status()` method to database
- Fixed message display order (message first, then status notifications)

### Module Changes
- `src/meshtui/connection.py` - ACK tracking, retry logic, timeout detection
- `src/meshtui/contact.py` - Automatic retry with flood routing
- `src/meshtui/channel.py` - Extract ACK codes (though not used for broadcasts)
- `src/meshtui/database.py` - New delivery tracking fields and update method
- `src/meshtui/app.py` - Immediate message display for contacts and channels

### API Limitations Addressed
- Channel broadcasts don't support ACK tracking (per MeshCore Python API design)
- Direct messages get full ACK tracking via `send_msg_with_retry()`
- Automatic fallback to flood routing after 2 failed attempts

## Previous Updates (2025-01-19)

### Per-Device Database Implementation
- **Feature**: Each connected device now gets its own database file
- **Location**: `~/.config/meshtui/devices/{device_pubkey[:16]}.db`
- **Benefit**: Prevents data collision when switching between different devices
- **Automatic**: Database is initialized after connection using device public key
- **Backward Compatible**: Legacy `meshtui.db` remains for reference

### Room Messaging Fix
- **Issue**: Room messages from other users were not appearing in real-time
- **Root Cause**: Database query was filtering out messages from other room participants
- **Fix**: Simplified room message query to show ALL messages to/from room
- **Result**: Room conversations now display messages from all participants in real-time

### Technical Improvements
- Added `_initialize_device_database()` method in connection.py
- Database initialization moved to post-connection phase
- Added safety checks for all database operations (`if self.db:`)
- Updated all three connection methods (BLE, Serial, TCP)
- Maintains backward compatibility with existing installations

## Recent Refactoring (Previous)

### Modular Architecture
- **Split into focused modules** for better maintainability
- **transport.py** - BLE, Serial, TCP connection handling
- **contact.py** - ContactManager for node/contact operations
- **channel.py** - ChannelManager for channel messaging
- **room.py** - RoomManager for room server authentication

### Features Added
- ✅ **Room server support** - Automatic detection and password login
- ✅ **Queued message retrieval** - Fetches messages after room login
- ✅ **Public channel messaging** - Send to channel 0 (public)
- ✅ **Node type detection** - Companion, Repeater, Room, Sensor
- ✅ **Contact-based chat** - Direct messaging to contacts
- ✅ **Channel selection** - Join and message channels
- ✅ **Message history** - View past conversations

### Architecture Benefits
1. **Separation of Concerns** - Each module has one job
2. **Easier Testing** - Test managers independently
3. **Better Maintainability** - Smaller, focused files
4. **Cleaner Code** - No 1000-line files!
5. **Type Safety** - Proper manager delegation

### Module Responsibilities

**app.py** (UI Layer)
- Textual widgets and user interface
- Delegates to connection manager
- No direct MeshCore API calls

**connection.py** (Orchestration)
- Initializes managers after connection
- Handles events and message storage
- Provides unified API to UI

**transport.py** (Connection Layer)
- SerialTransport - Port discovery
- BLETransport - Device scanning
- TCPTransport - Network connections

**contact.py** (Business Logic)
- Contact list management
- Node type detection
- Direct messaging

**channel.py** (Business Logic)
- Channel discovery
- Channel messaging
- Join/configure channels

**room.py** (Business Logic)  
- Room authentication
- Message queue fetching
- Login state tracking

## Previous Changes

### 1. ✅ Fixed Problems with Getting Contacts
- **Problem**: Contacts weren't being retrieved properly
- **Solution**: 
  - Added proper event subscription for `CONTACT_UPDATE` events
  - Enabled `auto_update_contacts` on the MeshCore instance
  - Fixed the contacts retrieval logic to properly handle the payload structure
  - Added contact change detection to avoid unnecessary UI updates
  - Implemented automatic contact refresh when new contacts are detected

### 2. ✅ Received Messages Not Being Shown
- **Problem**: Messages weren't being displayed in the chat area
- **Solution**:
  - Added event subscriptions for `CONTACT_MSG_RECV` and `CHANNEL_MSG_RECV`
  - Implemented message handlers that automatically update the UI when messages arrive
  - Added message storage with proper structure (sender, recipient, text, timestamp)
  - Implemented message filtering to show messages for the current selected contact
  - Added proper message display formatting with timestamps and sender names

### 3. ✅ No Public Channels or Hash Channels
- **Problem**: No support for public/hash channels
- **Solution**:
  - Added channels list to the UI sidebar
  - Implemented `get_channels()` method to retrieve available channels
  - Added support for joining channels via `join_channel(channel_name)`
  - Implemented channel message handling with proper event subscription
  - Added channel selection UI to switch between direct messages and channels
  - Added "Public" pseudo-channel to show all channel messages

### 4. ✅ No Way to Join Room Nodes
- **Problem**: Room nodes (repeaters) couldn't be joined/managed
- **Solution**:
  - Created dedicated "Node Management" tab in the UI
  - Implemented node list with refresh functionality
  - Added login/logout functionality for repeater nodes
  - Implemented command sending to repeaters
  - Added status request functionality for nodes
  - Created message waiting functionality for repeater responses

## Technical Improvements

### Connection Management (`connection.py`)
- Added proper event subscription system
- Implemented contact change detection
- Added message storage and retrieval
- Implemented channel management (list, join, message handling)
- Added repeater/node management methods
- Improved error handling and logging
- Added async event handlers for real-time updates

### UI Improvements (`app.py`)
- Added channels list sidebar
- Implemented contact selection with visual feedback
- Added channel selection support
- Created "Public" view for all channel messages
- Added Node Management tab with:
  - Node list display
  - Login/logout controls
  - Command sending interface
  - Status request functionality
- Improved message display with timestamps
- Added proper event handling for UI updates
- Fixed async method calls to properly await results

### Event Handling
- Subscribed to all relevant MeshCore events:
  - `CONTACT_UPDATE`: For contact list changes
  - `CONTACT_MSG_RECV`: For direct messages
  - `CHANNEL_MSG_RECV`: For channel messages
  - `NEW_CONTACT`: For new contact detection
  - `ADVERTISEMENT`: For network advertisements
  - `PATH_UPDATE`: For path changes

## Code Quality
- Created comprehensive `.github/copilot-instructions.md` for:
  - Python best practices with type hints and docstrings
  - MeshCore API patterns and usage
  - Textual UI patterns and conventions
  - Async/await guidelines
  - Error handling strategies
  - Testing considerations
  - Security and performance guidelines

## Testing
- Application successfully connects to MeshCore devices
- Contacts are properly retrieved and displayed
- Messages are received and shown in real-time
- Channels can be listed and joined
- Node management functionality is operational

## Usage Examples

### Viewing Contacts and Messages
1. Start the app: `python -m meshtui -s /dev/ttyUSB0`
2. Contacts appear in the left sidebar
3. Click a contact to view their messages
4. Type in the input field and press Enter or click Send

### Using Channels
1. Channels appear in the "Channels" section of the sidebar
2. Click "Public" to see all channel messages
3. Click a specific channel to filter messages
4. Use the input field to send messages to the selected channel

### Managing Nodes
1. Switch to the "Node Management" tab
2. Click "Refresh Nodes" to see available repeaters
3. Enter node name and password
4. Click "Login" to authenticate
5. Use "Send Command" to execute commands
6. Click "Get Status" to request node status

## Files Modified (Latest Changes)
- `src/meshtui/connection.py` - Per-device database initialization, safety checks
- `src/meshtui/database.py` - Simplified room message queries
- `src/meshtui/app.py` - Room message display in periodic refresh
- `CLAUDE.md` - Updated documentation for per-device databases
- `README.md` - Added per-device database section

## Files Modified (Previous Changes)
- `src/meshtui/connection.py` - Major enhancements to connection and event handling
- `src/meshtui/app.py` - UI improvements and new features
- `.github/copilot-instructions.md` - New comprehensive coding guidelines

## Dependencies
No new dependencies added. All features use existing meshcore API.
