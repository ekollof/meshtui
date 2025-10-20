# MeshTUI

MeshTUI: A Textual TUI interface to MeshCore companion radios

## Description

MeshTUI is a terminal user interface (TUI) client for interacting with MeshCore companion radios. Built with [Textual](https://textual.textualize.io/), it provides an intuitive, keyboard-driven interface for managing mesh networks, sending messages, and monitoring device status.

Unlike the command-line `meshcore-cli`, MeshTUI offers a visual interface with real-time updates, contact management, and chat functionality all in one terminal window.

## Features

- **Real-time chat interface** with contacts and channels
- **Message delivery tracking** - ACK tracking, retry logic, and delivery status
- **Device management** - scan, connect, and monitor MeshCore devices
- **Device identification** - automatically detects and identifies MeshCore devices
- **Contact management** - view, add, and manage mesh network contacts
- **Channel creation** - create custom encrypted channels with auto-hash support
- **Node management** - remote control of repeaters and room servers
- **Message history** - browse and search through message history with delivery status
- **Async operations** - built with asyncio for responsive UI
- **Multiple connection types** - BLE, TCP, and Serial support
- **Command line options** - specify connection method and device directly
- **Integrated log panel** - all logging output displayed in a dedicated panel within the TUI
- **Configuration persistence** - remembers device connections and settings
- **Automatic retry** - messages automatically retry with flood routing fallback
- **F1 Help** - comprehensive in-app help system

### Message Delivery Tracking

MeshTUI provides comprehensive message delivery tracking for direct messages:

- **✓ Sent** - Message successfully transmitted from your device
- **✓ Heard X repeats** - Number of repeaters that acknowledged forwarding the message
- **✗ Delivery failed** - No repeaters responded within timeout period
- **Automatic retry** - Up to 3 send attempts with intelligent flood routing fallback
- **Database tracking** - All delivery information stored for later analysis

**Note**: Channel broadcasts show "✓ Sent (broadcast)" and don't have ACK tracking (per MeshCore API design).

#### Delivery Status Database

All messages are tracked in the database with delivery information:

- `ack_code` - Unique acknowledgment code for tracking
- `delivery_status` - Current status: 'sent', 'repeated', 'failed', or 'broadcast'
- `repeat_count` - Number of repeater acknowledgments received
- `last_ack_time` - Timestamp of most recent acknowledgment

This allows you to review message delivery history and identify network issues.

## Installation

MeshTUI depends on the [python meshcore](https://github.com/fdlamotte/meshcore_py) package. You can install it via `pip` or `uv`:

```bash
uv tool install meshtui
```

This will install the `meshtui` command.

Alternatively, for development:

```bash
git clone <your-repo-url>
cd meshtui
uv pip install -e .
```

### Requirements

- Python >= 3.10
- A MeshCore-compatible radio device
- BLE support (if using Bluetooth connectivity)

## Usage

Launch MeshTUI with:

```bash
meshtui
```

### Command Line Options

MeshTUI supports various connection methods via command line arguments:

```bash
# Connect via serial (USB)
meshtui --serial /dev/ttyUSB0

# Connect via serial with custom baudrate
meshtui --serial /dev/ttyACM0 --baudrate 9600

# Connect via TCP/IP
meshtui --tcp 192.168.1.100 --port 5000

# Connect via BLE address
meshtui --address C2:2B:A1:D5:3E:B6

# Show help
meshtui --help
```

**Available options:**
- `-s, --serial SERIAL`: Connect via serial port (e.g., `/dev/ttyUSB0`)
- `-b, --baudrate BAUDRATE`: Serial baudrate (default: 115200)
- `-t, --tcp TCP`: Connect via TCP/IP hostname
- `-p, --port PORT`: TCP port (default: 5000)
- `-a, --address ADDRESS`: Connect via BLE address or name

### Device Identification

MeshTUI automatically identifies MeshCore devices:

- **BLE devices**: Scans for devices with names starting with "MeshCore-"
- **Serial devices**: Tests each serial port to identify MeshCore-compatible devices
- **Automatic prioritization**: Prefers `/dev/ttyUSB0` if available, then other serial devices, then BLE devices

When scanning, MeshTUI will show which devices are confirmed MeshCore devices with device information like model and firmware version.

### Interface Layout

MeshTUI features a three-panel layout:

- **Left Panel (Contacts)**: Shows available mesh network contacts
- **Center Panel (Tabbed)**: Contains Chat and Node Management tabs
- **Right Panel (Logs)**: Displays all application logs and connection status

### Node Management

MeshTUI includes comprehensive remote node management capabilities for repeaters and room servers:

#### **Node Management Tab Features:**

- **Node Discovery**: Automatically discovers available nodes in the mesh network
- **Node Login/Logout**: Authenticate with repeaters and room servers
- **Command Execution**: Send commands to remote nodes (no acknowledgment)
- **Status Monitoring**: Request and display node status information
- **Real-time Feedback**: All operations logged in the integrated log panel

#### **Node Management Workflow:**

1. **Refresh Nodes**: Click "Refresh Nodes" to scan for available nodes
2. **Login**: Enter node name and password, then click "Login"
3. **Send Commands**: Use the command input to send instructions to logged-in nodes
4. **Check Status**: Click "Get Status" to retrieve node information
5. **Logout**: Use the logout command when finished

#### **Supported Node Types:**

- **Repeaters**: Extend network coverage by relaying messages
- **Room Servers**: Provide shared messaging spaces (BBS-style)
- **Other Nodes**: Any meshcore-compatible remote device

### Creating Custom Channels

MeshTUI allows you to create encrypted channels for group communication:

#### **How to Create a Channel:**

1. Click the **"+"** button next to the "Channels" header in the sidebar
2. Enter a **channel slot** (1-7, slot 0 is reserved for Public channel)
3. Enter a **channel name**:
   - Use **# prefix** (e.g., `#mychannel`) for auto-generated hash-based secret
   - Or enter a custom name without # for manual secret management
4. Click **"Create"** to create the channel
5. The new channel appears in your channels list

#### **Channel Security:**

- Channels with **# prefix** automatically generate a 16-byte secret from the hash of the channel name
- Other devices can join by using the same channel name with # prefix
- Custom channels require manual secret exchange (16 bytes)
- All channel messages are encrypted using the channel secret

#### **Example:**

Creating a channel named `#team` will:
- Generate a consistent secret from hash("#team")
- Allow anyone with `#team` to decrypt messages
- Secure from others who don't know the channel name

### Key Bindings

- `Ctrl+C` - Quit the application
- `Ctrl+R` - Refresh current view
- `F1` - Show help
- `Tab` - Navigate between UI elements
- `Enter` - Send message or activate button

### First Time Setup

1. **Auto-connect**: MeshTUI attempts to connect automatically on startup
2. **Manual scan**: Click "Scan Devices" to manually search for devices
3. **Command line**: Specify device directly with command line options
4. **Start chatting**: Use the input field to send messages or commands

### Connection Process

When you specify a serial device (e.g., `--serial /dev/ttyUSB0`), MeshTUI:

1. **Opens the serial connection** at the specified baudrate (default: 115200)
2. **Sends a device query** to verify the device is a MeshCore-compatible radio
3. **Retrieves device information** (model, firmware version, capabilities)
4. **Sets up event handlers** for real-time contact and message updates
5. **Refreshes the contact list** from the device's memory

### Why Contacts Don't Appear

**Empty contact list is normal** for several reasons:

- **Single device setup**: If you're testing with only one MeshCore device, there are no other devices to communicate with
- **Fresh device**: New or factory-reset devices have no saved contacts
- **Network isolation**: Devices must be within radio range and on the same frequency/channel
- **No prior communication**: Contacts are only created after successful message exchanges

### How to Populate Contacts

To see contacts in the list:

1. **Add multiple devices** to your mesh network
2. **Send messages** between devices - this automatically creates contact entries
3. **Use the same frequency/channel** settings across devices
4. **Ensure devices are powered on** and within communication range
5. **Wait for advertisements** - devices periodically announce themselves

### Device Status Indicators

- **Connection successful**: Device info appears in logs (model, firmware, etc.)
- **Zero contacts**: Normal for single-device or new network setups
- **Communication working**: Messages sent/received successfully

## Troubleshooting

### Serial Port Permissions (Linux/macOS)

If you get permission errors when connecting via serial port, you need to add your user to the appropriate group:

**Linux:**
```bash
# Add your user to the dialout group
sudo usermod -a -G dialout $USER

# Log out and log back in for changes to take effect
# Or use: newgrp dialout
```

**macOS:**
```bash
# macOS typically doesn't require special permissions
# If you encounter issues, check /dev/tty.* or /dev/cu.* devices
ls -l /dev/tty.* /dev/cu.*
```

**Verify access:**
```bash
# Check group membership
groups

# Test device access (replace with your device path)
ls -l /dev/ttyUSB0
```

**Common error messages indicating permission issues:**
- "Permission denied" when opening serial port
- "Could not open port /dev/ttyUSB0"
- "Access denied"

### Log Files for Debugging

All application logs are automatically saved to a log file for postmortem analysis:

- **Location**: `$HOME/.config/meshtui/meshtui.log`
- **Content**: Includes DEBUG level logs with detailed connection and event information
- **Rotation**: Automatically rotates when reaching 5MB (keeps 3 backup files)
- **Usage**: Check this file when the application behaves unexpectedly or for detailed debugging

**Example log entries:**
```
2024-01-15 10:30:15 - meshtui - INFO - MeshTUI started - logging to ~/.config/meshtui/meshtui.log
2024-01-15 10:30:16 - meshtui.connection - INFO - Connected to Heltec V3 via serial. Found 2 contacts
2024-01-15 10:30:17 - meshtui.connection - DEBUG - 📡 EVENT: New contact detected: {'name': 'Device2', 'id': 123}
```

### Common Issues

- **Serial port permission denied**: Add your user to the `dialout` group (Linux) - see above
- **No contacts appearing**: See "Why Contacts Don't Appear" above
- **Connection fails**: Check serial port permissions and device power
- **Device not found**: Ensure the device is connected and appears in `/dev/ttyUSB*` or `/dev/ttyACM*`
- **Logs not updating**: Ensure the log panel is visible in the TUI
- **Performance issues**: Check log file size and rotate if necessary

## Configuration

Configuration files are stored in `$HOME/.config/meshtui/`

### Per-Device Databases

MeshTUI creates a separate database for each connected device to prevent data collision:

- **Location**: `$HOME/.config/meshtui/devices/{device_pubkey}.db`
- **Automatic**: Database is created on first connection to each device
- **Isolated**: Each device has its own messages, contacts, and settings
- **Seamless**: Switching devices automatically uses the correct database

When you connect to a device for the first time, a new database is created using the device's unique public key. This ensures that messages and contacts from one device don't mix with another device's data.

### Other Configuration Files

- **Device connections**: Preferences and last-used BLE address are saved
- **Message history**: All conversations persist between sessions
- **Log files**: All application logs are saved to `meshtui.log` for postmortem analysis
  - Location: `$HOME/.config/meshtui/meshtui.log`
  - Includes DEBUG level logs for detailed troubleshooting
  - Automatically rotates when reaching 5MB (keeps 3 backup files)
  - Use for debugging issues after the application closes

## Connection Types

MeshTUI supports the same connection methods as meshcore-cli:

- **BLE (Bluetooth Low Energy)**: Default for most companion radios
- **TCP/IP**: For network-connected devices
- **Serial**: For direct serial connections

## Commands and Features

MeshTUI provides access to all MeshCore functionality through an intuitive interface:

- **Messaging**: Send direct messages or broadcast to channels
- **Contacts**: Manage your mesh network contacts
- **Device Info**: View device status, telemetry, and configuration
- **Channels**: Join and participate in mesh channels
- **Repeaters**: Connect through mesh repeaters
- **Administration**: Device management and configuration

## Development

To contribute or modify MeshTUI:

1. Clone the repository
2. Create a virtual environment: `uv venv`
3. Activate: `source .venv/bin/activate` (Linux/Mac) or `.venv\Scripts\activate` (Windows)
4. Install dependencies: `uv pip install -e .`
5. Run: `python -m meshtui`

### Project Structure

```
src/meshtui/
├── app.py           # Main Textual application (UI layer)
├── app.css          # UI styling
├── connection.py    # Connection orchestration and lifecycle
├── transport.py     # BLE, Serial, TCP transport layers
├── contact.py       # Contact/node management
├── channel.py       # Channel operations
├── room.py          # Room server handling
├── database.py      # SQLite message and contact persistence
├── __init__.py      # Package initialization
└── __main__.py      # Entry point

docs/
└── meshcore-api/    # MeshCore API reference (copied from installed package)
    ├── README.md    # API documentation and examples
    ├── commands/    # Command modules (messaging, contacts, device)
    └── *.py         # Core API files
```

### API Reference

For MeshCore API reference, see `docs/meshcore-api/README.md`. This includes:
- Complete API documentation
- Command examples for messaging, contacts, and device management
- Event types and handling
- Room server administration
- Contact type definitions

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## Related Projects

- [meshcore-cli](https://github.com/fdlamotte/meshcore-cli) - Command-line interface
- [meshcore_py](https://github.com/fdlamotte/meshcore_py) - Python library for MeshCore
- [Textual](https://github.com/Textualize/textual) - TUI framework used by MeshTUI
</edit_description>
