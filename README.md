<edit_description>
Create README.md for the meshtui project
</edit_description>
# MeshTUI

MeshTUI: A Textual TUI interface to MeshCore companion radios

## Description

MeshTUI is a terminal user interface (TUI) client for interacting with MeshCore companion radios. Built with [Textual](https://textual.textualize.io/), it provides an intuitive, keyboard-driven interface for managing mesh networks, sending messages, and monitoring device status.

Unlike the command-line `meshcore-cli`, MeshTUI offers a visual interface with real-time updates, contact management, and chat functionality all in one terminal window.

## Features

- **Real-time chat interface** with contacts and channels
- **Device management** - scan, connect, and monitor MeshCore devices
- **Device identification** - automatically detects and identifies MeshCore devices
- **Contact management** - view, add, and manage mesh network contacts
- **Node management** - remote control of repeaters and room servers
- **Message history** - browse and search through message history
- **Async operations** - built with asyncio for responsive UI
- **Multiple connection types** - BLE, TCP, and Serial support
- **Command line options** - specify connection method and device directly
- **Integrated log panel** - all logging output displayed in a dedicated panel within the TUI
- **Configuration persistence** - remembers device connections and settings

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

- **No contacts appearing**: See "Why Contacts Don't Appear" above
- **Connection fails**: Check serial port permissions and device power
- **Logs not updating**: Ensure the log panel is visible in the TUI
- **Performance issues**: Check log file size and rotate if necessary

## Configuration

Configuration files are stored in `$HOME/.config/meshtui/`

- Device connections and preferences are automatically saved
- Message history and contact lists persist between sessions
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
├── app.py          # Main Textual application
├── app.css         # UI styling
├── __init__.py     # Package initialization
└── __main__.py     # Entry point
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## Related Projects

- [meshcore-cli](https://github.com/fdlamotte/meshcore-cli) - Command-line interface
- [meshcore_py](https://github.com/fdlamotte/meshcore_py) - Python library for MeshCore
- [Textual](https://github.com/Textualize/textual) - TUI framework used by MeshTUI
</edit_description>