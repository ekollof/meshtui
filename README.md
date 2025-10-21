# MeshTUI

MeshTUI: A Full-Featured MeshCore Client with Terminal UI

## Description

MeshTUI is a comprehensive terminal user interface (TUI) client for MeshCore devices. Built with [Textual](https://textual.textualize.io/), it provides a complete mesh networking experience with an intuitive, keyboard-driven interface for managing mesh networks, sending messages, administering nodes, and monitoring network status.

Unlike the command-line `meshcore-cli`, MeshTUI offers a rich visual interface with real-time updates, persistent message history, contact management, device configuration, and full node administration capabilities all in one terminal window.

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
- **TCP Proxy** (⚠️ Experimental) - Expose Serial/BLE devices over TCP for remote access
- **Command line options** - specify connection method and device directly
- **Integrated logs** - all logging output displayed in a dedicated Logs tab within the TUI
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

MeshTUI depends on the [python meshcore](https://github.com/fdlamotte/meshcore_py) package.

### PyPI Installation

You can install it via `pipx` or `uv`:

```bash
pipx install meshtui
# or
uv tool install meshtui
```

This will install the `meshtui` command globally and isolate its dependencies.

#### Optional: TCP Proxy Component

**⚠️ EXPERIMENTAL**: The TCP proxy is a new feature in active development.

To install with the TCP proxy component (allows exposing Serial/BLE devices over TCP):

```bash
pipx install meshtui[proxy]
# or
uv tool install meshtui[proxy]
```

This installs the `meshcore-tcp-proxy` command in addition to `meshtui`. See the [TCP Proxy](#tcp-proxy-experimental) section below for usage.

### Arch Linux

For Arch Linux users, PKGBUILD files are available in the `arch/` directory:

**Stable version (from PyPI):**
```bash
cd arch/meshtui
makepkg -si
```

**Development version (from git):**
```bash
cd arch/meshtui-git
makepkg -si
```

The `-git` version builds directly from the latest GitHub repository and conflicts with the stable package.

### Development Installation

For development, use `uv` or standard `pip`:

```bash
git clone <your-repo-url>
cd meshtui
uv pip install -e .
# or with pip in a virtual environment:
# python -m venv .venv && source .venv/bin/activate && pip install -e .
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

MeshTUI features a two-panel layout with tabbed content:

- **Left Sidebar**: Shows available mesh network contacts and channels
- **Main Content (Tabbed)**: Contains Chat, Device Settings, Node Management, and Logs tabs

### Node Management

MeshTUI includes comprehensive remote node management capabilities for repeaters and room servers:

#### **Node Management Tab Features:**

- **Node Discovery**: Automatically discovers available nodes in the mesh network
- **Node Login/Logout**: Authenticate with repeaters and room servers
- **Command Execution**: Send commands to remote nodes (no acknowledgment)
- **Status Monitoring**: Request and display node status information
- **Real-time Feedback**: All operations logged in the Logs tab

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
- **Logs not updating**: Switch to the Logs tab to view application logs
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
2. Create a virtual environment: `python -m venv .venv` or `uv venv`
3. Activate: `source .venv/bin/activate` (Linux/Mac) or `.venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -e .` or `uv pip install -e .`
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

## TCP Proxy (EXPERIMENTAL)

**⚠️ Status**: Experimental feature in active development (Phase 1 MVP complete)

The MeshCore TCP Proxy allows you to expose USB Serial or BLE-connected MeshCore devices over TCP/IP, enabling remote network access and TCP mode testing without WiFi firmware.

### Features

- **Zero protocol translation** - Identical framing across Serial/BLE/TCP
- **Multi-client support** - Multiple meshtui instances can connect simultaneously
- **Remote access** - Access locally-connected devices over network
- **TCP testing** - Test TCP connectivity without WiFi firmware

### Installation

```bash
# Install meshtui with proxy support
pipx install meshtui[proxy]
```

### Usage

**Start the proxy** (exposes serial device on TCP port 5000):
```bash
meshcore-tcp-proxy --serial /dev/ttyUSB0
```

**Connect meshtui via TCP**:
```bash
meshtui --tcp localhost --port 5000
```

### Advanced Options

```bash
# Custom port
meshcore-tcp-proxy --serial /dev/ttyUSB0 --port 6000

# Debug mode with frame logging
meshcore-tcp-proxy --serial /dev/ttyUSB0 --debug --log-frames

# Use config file
meshcore-tcp-proxy --config /path/to/config.yaml

# Remote access (listen on all interfaces)
meshcore-tcp-proxy --serial /dev/ttyUSB0 --host 0.0.0.0
```

### Configuration File

Example configuration (`config.yaml`):
```yaml
proxy:
  listen_host: 0.0.0.0
  listen_port: 5000

backend:
  type: serial
  serial_port: /dev/ttyUSB0
  baudrate: 115200
  auto_reconnect: true

logging:
  level: INFO
  log_frames: false
```

See `config/proxy/config.yaml.example` for full configuration options.

### Architecture

The proxy consists of:
- **Serial Backend** - Connects to USB serial devices (Phase 1 ✅)
- **TCP Server** - Accepts multiple client connections
- **Frame Router** - Bidirectional forwarding (no protocol translation)
- **BLE Backend** - Bluetooth LE support (Phase 3, planned)

### Documentation

Complete design documentation: `docs/MESHCORE_TCP_PROXY_DESIGN.md`

### Limitations (Phase 1)

- Serial backend only (BLE support planned for Phase 3)
- No authentication/encryption (use SSH tunnel or VPN for remote access)
- Experimental status - may have bugs or breaking changes

### Roadmap

- **Phase 1** (✅ Complete): Serial backend, basic TCP server
- **Phase 2** (Planned): Multi-client enhancements, session management
- **Phase 3** (Planned): BLE backend support
- **Phase 4** (Planned): Auto-reconnect, health monitoring, robustness
- **Phase 5** (Planned): Systemd service, packaging, deployment tools

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## Related Projects

- [meshcore-cli](https://github.com/fdlamotte/meshcore-cli) - Command-line interface
- [meshcore_py](https://github.com/fdlamotte/meshcore_py) - Python library for MeshCore
- [Textual](https://github.com/Textualize/textual) - TUI framework used by MeshTUI
</edit_description>
