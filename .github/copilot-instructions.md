# GitHub Copilot Instructions for MeshTUI

## Project Overview

MeshTUI is a Textual-based TUI (Terminal User Interface) application for interfacing with MeshCore companion radios. This project provides a rich terminal interface for managing mesh network communications, contacts, channels, and node management.

## Code Style and Standards

### Python Best Practices

1. **Type Hints**: Always use type hints for function parameters and return values
   ```python
   async def send_message(self, recipient: str, message: str) -> bool:
   ```

2. **Docstrings**: Use comprehensive docstrings for all public methods and classes
   ```python
   async def refresh_contacts(self):
       """Refresh the contacts list from the connected MeshCore device.
       
       This method updates the internal contacts list by querying the device
       and ensures the UI is synchronized with the latest contact information.
       """
   ```

3. **Error Handling**: Always wrap async operations in try-catch blocks with proper logging
   ```python
   try:
       result = await asyncio.wait_for(self.meshcore.commands.get_contacts(), timeout=5.0)
   except asyncio.TimeoutError:
       self.logger.error("Timeout refreshing contacts")
   except Exception as e:
       self.logger.error(f"Failed to refresh contacts: {e}")
   ```

4. **Logging**: Use structured logging with appropriate levels
   ```python
   self.logger.info(f"Successfully connected to {device_name}")
   self.logger.debug(f"Device info: {device_info}")
   self.logger.error(f"Connection failed: {error}")
   ```

### MeshCore API Patterns

1. **Connection Management**: Always check connection status before operations
   ```python
   if not self.meshcore or not self.meshcore.is_connected:
       return False
   ```

2. **Command Execution**: Access commands through the `commands` attribute
   ```python
   result = await self.meshcore.commands.get_contacts()
   if result.type != EventType.ERROR:
       # Process successful result
   ```

3. **Event Handling**: Subscribe to relevant events for reactive updates
   ```python
   self.meshcore.subscribe(EventType.CONTACT_MSG_RECV, self._handle_contact_message)
   self.meshcore.subscribe(EventType.CHANNEL_MSG_RECV, self._handle_channel_message)
   ```

4. **Async Best Practices**: Use timeouts for all async operations
   ```python
   result = await asyncio.wait_for(operation(), timeout=5.0)
   ```

### Textual UI Patterns

1. **Widget References**: Store widget references in `on_mount()` for efficient access
   ```python
   def on_mount(self) -> None:
       self.chat_area = self.query_one("#chat-area", TextArea)
       self.contacts_list = self.query_one("#contacts-list", ListView)
   ```

2. **Event Handlers**: Use the `@on` decorator for clean event handling
   ```python
   @on(Button.Pressed, "#send-btn")
   async def send_message(self) -> None:
   ```

3. **UI Updates**: Always update UI elements from the main thread
   ```python
   # Good: Direct UI update
   self.chat_area.insert(f"[green]{sender}:[/green] {message}\n")
   ```

### Git Operations

**IMPORTANT: Always use GitKraken tools for git operations**

- Use `mcp_gitkraken_git_add_or_commit` with `action: "add"` to stage files
- Use `mcp_gitkraken_git_add_or_commit` with `action: "commit"` to commit changes
- Use `mcp_gitkraken_git_push` to push changes
- Use `mcp_gitkraken_git_blame` to view file history
- Never use terminal commands like `git add`, `git commit`, etc.

Example commit workflow:
```python
# Stage all changes
mcp_gitkraken_git_add_or_commit(action="add", directory="/path/to/repo")

# Commit with message
mcp_gitkraken_git_add_or_commit(
    action="commit", 
    directory="/path/to/repo",
    message="Descriptive commit message"
)
```

### Async Best Practices

1. **Concurrency**: Use `asyncio.wait_for()` for timeout protection
2. **Task Management**: Properly clean up background tasks in `disconnect()`
3. **Error Propagation**: Let async exceptions bubble up with proper logging

### Project Structure

```
src/meshtui/
├── __init__.py          # Package initialization
├── __main__.py          # Entry point for python -m meshtui
├── app.py              # Main Textual application class (UI layer)
├── app.css            # Textual CSS styling
├── connection.py       # Connection orchestration and lifecycle
├── transport.py        # NEW: BLE, Serial, TCP transport layers
├── contact.py          # NEW: Contact/node management
├── channel.py          # NEW: Channel operations
└── room.py            # NEW: Room server handling
```

### Architecture Overview

**Layered Architecture:**
- **UI Layer** (`app.py`) - Textual widgets and user interaction
- **Connection Layer** (`connection.py`) - Orchestrates managers and transport
- **Manager Layer** (`contact.py`, `channel.py`, `room.py`) - Business logic
- **Transport Layer** (`transport.py`) - Low-level connection handling

**Design Principles:**
- **Separation of Concerns** - Each module has a single responsibility
- **Dependency Injection** - Managers receive MeshCore instance
- **Event-Driven** - React to MeshCore events, don't poll
- **Async First** - All I/O operations are async

## Specific Implementation Guidelines

### Module Responsibilities

**`app.py` - UI Layer**
- Textual application and widgets
- User input handling and display
- Delegates operations to connection manager
- No direct MeshCore API calls

**`connection.py` - Orchestration**
- Initializes and manages transport, contacts, channels, rooms
- Handles connection lifecycle and event subscriptions
- Provides unified interface to UI layer
- Message storage and retrieval

**`transport.py` - Connection Types**
- `SerialTransport` - Serial port discovery and connection
- `BLETransport` - Bluetooth LE scanning and pairing
- `TCPTransport` - Network connection handling
- Returns connected MeshCore instances

**`contact.py` - Contact Management**
- `ContactManager` - Maintains contact list
- Contact lookup by name/key
- Node type detection (companion, repeater, room, sensor)
- Direct messaging to contacts

**`channel.py` - Channel Operations**
- `ChannelManager` - Channel discovery and joining
- Send messages to channels
- Public channel (index 0) handling
- Channel configuration

**`room.py` - Room Servers**
- `RoomManager` - Room authentication and messaging
- Login/logout from room servers
- Automatic message queue retrieval
- Tracks login state per room

### Connection Management

- Always use manager interfaces rather than direct MeshCore access
- Transport layer handles low-level connection details
- Connection manager initializes all managers after connection:
  ```python
  self.contacts = ContactManager(meshcore)
  self.channels = ChannelManager(meshcore)
  self.rooms = RoomManager(meshcore, messages)
  ```
- Implement proper cleanup in `disconnect()` methods
- Handle connection state changes gracefully
- Use event-driven updates where possible

### Working with Managers

**Contact Operations:**
```python
# Refresh contacts
await self.connection.contacts.refresh()

# Get contact by name
contact = self.connection.contacts.get_by_name("NodeName")

# Check node type
if self.connection.contacts.is_room_server(contact):
    # Handle room server
```

**Channel Operations:**
```python
# Send to channel
await self.connection.channels.send_message(0, "Hello public!")

# Get channels
channels = await self.connection.channels.get_channels()
```

**Room Operations:**
```python
# Login to room
success = await self.connection.rooms.login(room_name, room_key, password)

# Check login status
if self.connection.rooms.is_logged_in(room_name):
    # Send messages
```

### Message Handling

- Support both direct messages (`CONTACT_MSG_RECV`) and channel messages (`CHANNEL_MSG_RECV`)
- Room messages are fetched automatically after successful login
- Store received messages for retrieval and display
- Implement message filtering and display by type
- Handle message timestamps properly

**CRITICAL: Always use Public Keys for Lookups**
- **NEVER** compare or lookup contacts by display names
- **ALWAYS** use public keys (pubkeys) for identity verification and comparison
- Messages may contain short pubkey prefixes - handle both full keys and prefixes
- Example comparison:
  ```python
  # GOOD: Pubkey comparison
  if sender_pubkey == my_pubkey or my_pubkey.startswith(sender_pubkey):
      is_from_me = True
  
  # BAD: Name comparison
  if sender == "Me":  # Names can be spoofed!
      is_from_me = True
  ```
- Use `ContactManager.get_by_key()` for contact lookups
- Store and compare `sender_pubkey`, `recipient_pubkey`, `actual_sender_pubkey`, and `signature` fields
- Names are for display only, pubkeys are for identity

### Node Type Detection

MeshCore contacts have a `type` field:
- `0` or `1` = Companion node (regular contact)
- `2` = Repeater node
- `3` = Room server (requires password authentication)
- `4` = Sensor node

Use `ContactManager` methods for type checking:
```python
if self.connection.contacts.is_room_server(contact):
    # Prompt for password before messaging
if self.connection.contacts.is_repeater(contact):
    # Handle repeater-specific logic
```

### UI Responsiveness

- Use background tasks for long-running operations
- Provide user feedback for all operations
- Handle connection failures gracefully
- Update UI reactively to connection events

### Error Handling Strategy

1. **Log Errors**: Always log errors with context
2. **User Feedback**: Provide clear error messages in the UI
3. **Graceful Degradation**: Continue operating when possible
4. **Recovery**: Attempt reconnection when appropriate

## Testing Considerations

- Mock MeshCore connections for unit tests
- Test UI state changes independently
- Verify async operation timeouts
- Test error handling paths

## Documentation Standards

- Keep README.md updated with features and usage
- Document all configuration options
- Provide troubleshooting guides
- Include API usage examples

## Security Considerations

- Handle device passwords securely
- Validate all user inputs
- Sanitize data from mesh network
- Log security-relevant events

## Performance Guidelines

- Use efficient data structures for contacts and messages
- Implement lazy loading for large data sets
- Cache frequently accessed data
- Minimize UI update frequency

When contributing to this project, follow these guidelines to maintain code quality and consistency. Always test changes thoroughly with actual MeshCore hardware when possible.