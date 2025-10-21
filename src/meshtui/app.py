#!/usr/bin/env python3
"""
meshtui - Full-featured MeshCore client with Terminal UI
"""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Optional

try:
    import notify2

    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Click
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    ListView,
    ListItem,
    Log,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)
from textual.binding import Binding

from .connection import MeshConnection


class InstantButton(Button):
    """Button that activates on first click without requiring focus."""

    async def _on_click(self, event: Click) -> None:
        """Handle click event to activate immediately."""
        event.stop()
        self.press()


def sanitize_id(name: str) -> str:
    """Convert a name to a valid HTML/CSS ID.

    Args:
        name: The name to sanitize

    Returns:
        Valid ID string with only letters, numbers, underscores, and hyphens
    """
    # Replace spaces and invalid characters with underscores
    import re

    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    # Ensure it doesn't start with a number
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


class TextualLogHandler(logging.Handler):
    """Custom logging handler that writes to a Textual Log widget."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def emit(self, record):
        """Emit a log record to the Textual log panel."""
        try:
            msg = self.format(record)
            # Write directly, assuming logging happens in main thread
            if hasattr(self.app, "log_panel") and self.app.log_panel:
                self._write_to_log(msg)
            else:
                # Fallback: print to stdout if log panel not available
                print(f"LOG: {msg}")
        except Exception as e:
            print(f"Logging error: {e}")
            self.handleError(record)

    def _write_to_log(self, message):
        """Write message to the log panel."""
        try:
            if hasattr(self.app, "log_panel") and self.app.log_panel:
                self.app.log_panel.write(message + "\n")
            else:
                print(f"LOG FALLBACK: {message}")
        except Exception as e:
            print(f"Log write error: {e}")


class MeshTUI(App):
    """Main Textual application for meshcore TUI client."""

    TITLE = "MeshTUI"
    SUB_TITLE = "MeshCore Companion Radio TUI"
    CSS_PATH = "app.css"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("f1", "show_help", "Help"),
    ]

    def __init__(self, args):
        super().__init__()
        self.args = args
        self.connection = MeshConnection()
        self.current_contact = None  # Contact name (for display/compatibility)
        self.current_contact_pubkey = None  # Contact public_key (canonical identifier)
        self.current_channel = None
        self._awaiting_room_password = False  # Flag for room password input
        self._contact_id_map = {}  # Map sanitized IDs back to contact names
        self._channel_id_map = {}  # Map sanitized IDs back to channel names
        self.messages = []

        # Setup logging (will be configured in on_mount)
        self.logger = logging.getLogger("meshtui")
        self.logger.setLevel(logging.DEBUG)  # Enable debug logging

        # Setup desktop notifications
        self.notifications_enabled = False
        if NOTIFICATIONS_AVAILABLE:
            try:
                notify2.init("MeshTUI")
                self.notifications_enabled = True
                self.logger.info("Desktop notifications enabled")
            except Exception as e:
                self.logger.warning(f"Failed to initialize notifications: {e}")
        else:
            self.logger.info("notify2 not available, desktop notifications disabled")

    def compose(self) -> ComposeResult:
        """Compose the UI layout."""
        yield Header()

        with Horizontal():
            # Left sidebar - Contacts and Channels
            with Vertical(id="sidebar"):
                yield Static("Contacts", id="contacts-header")
                yield ListView(id="contacts-list")

                with Horizontal(id="channels-header-row"):
                    yield Static("Channels", id="channels-header")
                    yield Button("+", id="create-channel-btn", variant="success")
                yield ListView(id="channels-list")

                # Instant-click buttons for sidebar
                yield InstantButton(
                    "Scan BLE Devices", id="scan-ble-btn", variant="primary"
                )
                yield InstantButton(
                    "Send Advert (0-hop)", id="advert-0hop-btn", variant="primary"
                )
                yield InstantButton(
                    "Send Advert (Flood)", id="advert-flood-btn", variant="default"
                )

            # Main content area with tabs
            with Vertical(id="main-content"):
                with TabbedContent():
                    with TabPane("Chat", id="chat-tab"):
                        with Vertical(id="chat-container"):
                            # Chat area - using RichLog to support markup
                            yield RichLog(id="chat-area", highlight=True, markup=True)

                            # Input area
                            with Horizontal(id="input-container"):
                                yield Input(
                                    placeholder="Type message or command...",
                                    id="message-input",
                                )
                                yield Button("Send", id="send-btn", variant="primary")

                    with TabPane("Contact Info", id="contact-info-tab"):
                        # Contact information and management (scrollable)
                        from textual.containers import VerticalScroll
                        with VerticalScroll(id="contact-info-container"):
                            yield Static("Contact Information", id="contact-info-header")
                            yield Static(
                                "Select a contact to view details",
                                id="contact-info-status",
                                classes="help-text",
                            )

                            # Two-column layout: Contact details + Network path
                            with Horizontal(id="contact-details-row"):
                                # Left column: Contact details
                                with Vertical(id="contact-details-column"):
                                    yield Static("[bold]Contact Details[/bold]", classes="section-title")
                                    with Horizontal():
                                        yield Static("Name:", classes="label")
                                        yield Static("", id="contact-name-display")
                                    with Horizontal():
                                        yield Static("Public Key:", classes="label")
                                        yield Static("", id="contact-pubkey-display")
                                    with Horizontal():
                                        yield Static("Type:", classes="label")
                                        yield Static("", id="contact-type-display")
                                    with Horizontal():
                                        yield Static("Last Seen:", classes="label")
                                        yield Static("", id="contact-lastseen-display")

                                # Right column: Network path info
                                with Vertical(id="contact-network-column"):
                                    yield Static("[bold]Network Path[/bold]", classes="section-title")
                                    yield Static(
                                        "Routing path to this contact",
                                        classes="help-text",
                                    )
                                    yield Static("Click 'Trace Path' to discover route", id="contact-path-display")
                                    yield Button("Trace Path", id="trace-path-btn", variant="default")

                            # Notes section (full width)
                            yield Static("[bold]Notes[/bold]", classes="section-title")
                            yield Static(
                                "Personal notes about this contact (saved locally)",
                                classes="help-text",
                            )
                            from textual.widgets import TextArea
                            yield TextArea(id="contact-notes-input", language="markdown")
                            yield Button("Save Notes", id="save-notes-btn", variant="primary")

                            # Actions section
                            yield Static("[bold]Actions[/bold]", classes="section-title")
                            with Horizontal():
                                yield Button("Ping", id="ping-btn", variant="default")
                                yield Button(
                                    "Delete Contact",
                                    id="delete-contact-btn",
                                    variant="error",
                                )

                    with TabPane("Device Settings", id="settings-tab"):
                        # Device configuration area
                        with Vertical(id="settings-container"):
                            yield Static("Device Configuration", id="settings-header")
                            yield Static(
                                "Configure your connected MeshCore device",
                                classes="help-text",
                            )

                            # Device Info Section
                            yield Static(
                                "[bold]Device Information[/bold]",
                                classes="section-title",
                            )
                            with Horizontal():
                                yield Static("Device Name:", classes="label")
                                yield Input(
                                    placeholder="Device name", id="settings-name-input"
                                )
                                yield Button(
                                    "Set Name",
                                    id="settings-name-btn",
                                    variant="primary",
                                )

                            # Radio Configuration Section
                            yield Static(
                                "[bold]Radio Configuration[/bold]",
                                classes="section-title",
                            )
                            with Horizontal():
                                yield Static("TX Power (dBm):", classes="label")
                                yield Input(
                                    placeholder="TX power", id="settings-tx-power-input"
                                )
                                yield Button(
                                    "Set", id="settings-tx-power-btn", variant="primary"
                                )

                            with Horizontal():
                                yield Static("Frequency (MHz):", classes="label")
                                yield Input(
                                    placeholder="915.0", id="settings-freq-input"
                                )
                                yield Static("Bandwidth (kHz):", classes="label")
                                yield Input(placeholder="125.0", id="settings-bw-input")
                            with Horizontal():
                                yield Static("Spread Factor:", classes="label")
                                yield Input(placeholder="7-12", id="settings-sf-input")
                                yield Static("Coding Rate:", classes="label")
                                yield Input(placeholder="5-8", id="settings-cr-input")
                                yield Button(
                                    "Set Radio",
                                    id="settings-radio-btn",
                                    variant="primary",
                                )

                            # Location Section
                            yield Static(
                                "[bold]Location[/bold]", classes="section-title"
                            )
                            with Horizontal():
                                yield Static("Latitude:", classes="label")
                                yield Input(placeholder="0.0", id="settings-lat-input")
                                yield Static("Longitude:", classes="label")
                                yield Input(placeholder="0.0", id="settings-lon-input")
                                yield Button(
                                    "Set Coords",
                                    id="settings-coords-btn",
                                    variant="primary",
                                )

                            # Device Actions Section
                            yield Static(
                                "[bold]Device Actions[/bold]", classes="section-title"
                            )
                            with Horizontal():
                                yield Button(
                                    "Reboot Device",
                                    id="settings-reboot-btn",
                                    variant="error",
                                )
                                yield Button(
                                    "Get Battery Info", id="settings-battery-btn"
                                )
                                yield Button("Sync Time", id="settings-time-btn")

                            # Status output area
                            yield Static("Status:", classes="section-label")
                            yield RichLog(
                                id="settings-status-area",
                                auto_scroll=True,
                                wrap=True,
                                markup=True,
                            )

                    with TabPane("Node Management", id="node-tab"):
                        # Node management area (for repeaters and sensors)
                        with Horizontal():
                            # Left: Command cheat sheet
                            with Vertical(id="node-list-container"):
                                yield Static("Command Reference", id="nodes-header")
                                yield RichLog(id="command-reference", auto_scroll=False)

                            # Right: Node control panel
                            with Vertical(id="node-control-container"):
                                yield Static(
                                    "Node Administration", id="node-control-header"
                                )
                                yield Static(
                                    "For Repeaters (type 2) and Sensors (type 4)",
                                    classes="help-text",
                                )
                                yield Static(
                                    "Room admin: Login via Chat tab with admin password",
                                    classes="help-text",
                                )
                                yield Static(
                                    "Tip: Leave node name blank to use current chat contact",
                                    classes="help-text",
                                )

                                # Login section (for repeaters only)
                                yield Static("Repeater Login:", classes="section-label")
                                with Horizontal():
                                    yield Input(
                                        placeholder="Repeater name",
                                        id="node-name-input",
                                    )
                                    yield Input(
                                        placeholder="Password",
                                        id="node-password-input",
                                        password=True,
                                    )
                                    yield Button(
                                        "Login", id="node-login-btn", variant="primary"
                                    )

                                # Command section (works for repeaters, rooms if admin, sensors)
                                yield Static("Send Command:", classes="section-label")
                                with Horizontal():
                                    yield Input(
                                        placeholder="Node name (repeater/room/sensor)",
                                        id="node-cmd-target-input",
                                    )
                                    yield Input(
                                        placeholder="Command (e.g., 'help', 'status')",
                                        id="node-command-input",
                                    )
                                    yield Button(
                                        "Send",
                                        id="node-send-cmd-btn",
                                        variant="primary",
                                    )

                                # Status section
                                yield Static("Request Status:", classes="section-label")
                                with Horizontal():
                                    yield Input(
                                        placeholder="Node name",
                                        id="node-status-target-input",
                                    )
                                    yield Button(
                                        "Get Status",
                                        id="node-status-btn",
                                        variant="primary",
                                    )

                                # Output area
                                yield Static("Output:", classes="section-label")
                                yield RichLog(
                                    id="node-status-area", auto_scroll=True, wrap=True
                                )

                    with TabPane("Logs", id="logs-tab"):
                        # Application logs
                        with Vertical(id="logs-container"):
                            yield Static("Application Logs", id="logs-header")
                            yield Static(
                                "Debug and status messages from MeshTUI",
                                classes="help-text",
                            )
                            yield Log(id="log-panel", auto_scroll=True)

        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        # Setup UI references first
        self.contacts_list = self.query_one("#contacts-list", ListView)
        self.channels_list = self.query_one("#channels-list", ListView)
        self.chat_area = self.query_one("#chat-area", RichLog)
        self.message_input = self.query_one("#message-input", Input)
        self.log_panel = self.query_one("#log-panel", Log)

        # Tab references for showing/hiding
        self.tabbed_content = self.query_one(TabbedContent)

        # Contact Info UI references
        from textual.widgets import TextArea
        self.contact_name_display = self.query_one("#contact-name-display", Static)
        self.contact_pubkey_display = self.query_one("#contact-pubkey-display", Static)
        self.contact_type_display = self.query_one("#contact-type-display", Static)
        self.contact_lastseen_display = self.query_one("#contact-lastseen-display", Static)
        self.contact_path_display = self.query_one("#contact-path-display", Static)
        self.contact_notes_input = self.query_one("#contact-notes-input", TextArea)
        self.contact_info_status = self.query_one("#contact-info-status", Static)

        # Device settings UI references
        self.settings_name_input = self.query_one("#settings-name-input", Input)
        self.settings_tx_power_input = self.query_one("#settings-tx-power-input", Input)
        self.settings_freq_input = self.query_one("#settings-freq-input", Input)
        self.settings_bw_input = self.query_one("#settings-bw-input", Input)
        self.settings_sf_input = self.query_one("#settings-sf-input", Input)
        self.settings_cr_input = self.query_one("#settings-cr-input", Input)
        self.settings_lat_input = self.query_one("#settings-lat-input", Input)
        self.settings_lon_input = self.query_one("#settings-lon-input", Input)
        self.settings_status_area = self.query_one("#settings-status-area", RichLog)

        # Node management UI references
        self.command_reference = self.query_one("#command-reference", RichLog)
        self.node_name_input = self.query_one("#node-name-input", Input)
        self.node_password_input = self.query_one("#node-password-input", Input)
        self.node_cmd_target_input = self.query_one("#node-cmd-target-input", Input)
        self.node_command_input = self.query_one("#node-command-input", Input)
        self.node_status_target_input = self.query_one(
            "#node-status-target-input", Input
        )
        self.node_status_area = self.query_one("#node-status-area", RichLog)

        # Populate command reference cheat sheet
        self._populate_command_reference()

        # Setup logging handler now that we have the log panel
        self.log_handler = TextualLogHandler(self)
        self.log_handler.setLevel(logging.INFO)  # TUI shows INFO+ only
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

        # Add handler to root logger to capture all logging
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)

        self.logger.info("MeshTUI started - logging to ~/.config/meshtui/meshtui.log")

        # Register message callback for notifications
        self.connection.set_message_callback(self._on_new_message)

        # Register contacts callback for UI updates
        self.connection.set_contacts_callback(self._on_contacts_updated)

        # Try to auto-connect if possible (schedule after mount)
        self.call_later(lambda: asyncio.create_task(self.auto_connect()))

        # Start periodic message refresh (every 2 seconds)
        self.set_interval(2.0, self.periodic_message_refresh)

    def _populate_command_reference(self):
        """Populate the command reference cheat sheet."""
        from rich.text import Text

        self.command_reference.write(Text("Common Commands:", style="bold yellow"))
        self.command_reference.write("")

        # General commands
        self.command_reference.write(Text("Information:", style="bold cyan"))
        self.command_reference.write("  status    - System status")
        self.command_reference.write("  ver       - Firmware version")
        self.command_reference.write("  clock     - Show current time")
        self.command_reference.write("")

        # Clock commands
        self.command_reference.write(Text("Time Sync:", style="bold cyan"))
        self.command_reference.write("  clock sync      - Sync time")
        self.command_reference.write("  clock set <ts>  - Set Unix timestamp")
        self.command_reference.write("")

        # Room commands
        self.command_reference.write(Text("Room Admin:", style="bold cyan"))
        self.command_reference.write("  list_users  - Show logged in users")
        self.command_reference.write("  kick <user> - Kick user from room")
        self.command_reference.write("  ban <user>  - Ban user from room")
        self.command_reference.write("")

        # Network commands
        self.command_reference.write(Text("Network:", style="bold cyan"))
        self.command_reference.write("  neighbors  - Show nearby nodes")
        self.command_reference.write("  path       - Show routing path")
        self.command_reference.write("")

        # Radio config
        self.command_reference.write(Text("Radio Settings:", style="bold cyan"))
        self.command_reference.write("  get_config        - Show config")
        self.command_reference.write("  set lora_sf <n>   - Spreading factor")
        self.command_reference.write("  set lora_bw <khz> - Bandwidth")
        self.command_reference.write("  set tx_power <n>  - TX power")
        self.command_reference.write("  reboot            - Reboot node")

    def _on_contacts_updated(self):
        """Callback when contacts list is updated."""
        self.logger.debug("📋 Contacts list updated, refreshing UI")
        # Schedule UI update
        self.call_later(lambda: asyncio.create_task(self.update_contacts()))

    def _send_desktop_notification(
        self, title: str, message: str, urgency: str = "normal"
    ):
        """Send a desktop notification via D-Bus.

        Args:
            title: Notification title
            message: Notification message body
            urgency: Urgency level: 'low', 'normal', or 'critical'
        """
        if not self.notifications_enabled:
            return

        try:
            # Use network-wireless icon for mesh network messages
            n = notify2.Notification(title, message, "network-wireless")
            urgency_map = {"low": 0, "normal": 1, "critical": 2}
            n.set_urgency(urgency_map.get(urgency, 1))
            n.show()
            self.logger.debug(f"Sent desktop notification: {title}")
        except Exception as e:
            self.logger.warning(f"Failed to send desktop notification: {e}")

    def _on_new_message(
        self,
        sender: str,
        text: str,
        msg_type: str,
        channel_name: Optional[str] = None,
        txt_type: int = 0,
    ):
        """Callback when a new message arrives.

        Args:
            sender: Name of the sender
            text: Message text
            msg_type: Type of message ('contact', 'room', 'channel', or 'ack')
            channel_name: Channel name if msg_type is 'channel'
            txt_type: Text type (0=regular message, 1=command response)
        """
        # Handle status notifications (sent/ACK from repeaters)
        if msg_type == "status":
            self.logger.debug(f"📋 Status notification: {text}")
            try:
                # Show status in chat area if we're viewing a channel or contact
                if self.current_contact or self.current_channel:
                    self.chat_area.write(f"[dim]{text}[/dim]")
            except Exception as e:
                self.logger.error(f"Failed to display status: {e}")
            return

        # Handle ACK notifications (message repeated by repeater) - legacy
        if msg_type == "ack":
            self.logger.debug(f"📋 ACK notification: {text}")
            try:
                # Show ACK in chat area if we're viewing a channel or contact
                if self.current_contact or self.current_channel:
                    self.chat_area.write(f"[dim]{text}[/dim]")
            except Exception as e:
                self.logger.error(f"Failed to display ACK: {e}")
            return

        # Route command responses (txt_type=1) to Node Management output
        if txt_type == 1:
            self.logger.debug(f"📋 Command response from {sender}: {text}")
            try:
                from rich.text import Text

                # Create Rich Text with proper styling
                output = Text()
                if sender:
                    output.append(sender, style="cyan")
                    output.append(": ")
                output.append(text)
                self.node_status_area.write(output)
            except Exception as e:
                self.logger.error(f"Failed to display command response: {e}")
            # Return early - don't show command responses in chat
            return

        # Check if this message is for the current view
        is_current_view = False

        self.logger.debug(
            f"🔍 Message callback: sender={sender}, msg_type={msg_type}, channel={channel_name}, current_contact={self.current_contact}, current_channel={self.current_channel}"
        )

        if (
            msg_type == "contact" or msg_type == "room"
        ) and self.current_contact == sender:
            is_current_view = True
        elif msg_type == "channel" and channel_name:
            is_current_view = self.current_channel == channel_name or (
                channel_name == "Public" and self.current_channel == "Public"
            )

        self.logger.debug(f"🔍 is_current_view={is_current_view}")

        if is_current_view:
            # Message is for current view - refresh immediately and mark as read
            self.logger.info(
                f"✅ New message in current view from {sender}, refreshing display"
            )
            self.connection.mark_as_read(sender)
            asyncio.create_task(self.refresh_messages())
            # Update the display to clear the unread count
            if msg_type in ("contact", "room"):
                self._update_single_contact_display(sender)
            elif msg_type == "channel" and channel_name:
                self._update_single_channel_display(channel_name)
        else:
            # Message is from another contact/channel - show notification and update that contact's unread indicator
            source = channel_name if msg_type == "channel" else sender
            preview = text[:50] + "..." if len(text) > 50 else text
            self.logger.info(f"💬 New message from {source}: {preview}")

            # Send desktop notification
            self._send_desktop_notification(
                "MeshTUI - Message Received",
                f"{source}: {preview}",
                urgency="normal",
            )

            # Send in-app notification
            self.notify(
                f"New message from {source}",
                title="Message Received",
                severity="information",
            )
            # Update just this contact/channel's display to show new unread count
            if msg_type in ("contact", "room"):
                self.logger.debug(
                    f"🔍 Calling _update_single_contact_display for {sender}"
                )
                self._update_single_contact_display(sender)
            elif msg_type == "channel" and channel_name:
                self.logger.debug(
                    f"🔍 Calling _update_single_channel_display for {channel_name}"
                )
                self._update_single_channel_display(channel_name)

    def _update_single_contact_display(self, contact_name: str) -> None:
        """Update the display of a single contact in the list to reflect new unread count.

        Args:
            contact_name: Name of the contact to update
        """
        try:
            # Find the contact's ListItem widget
            contact_id = f"contact-{sanitize_id(contact_name)}"
            list_item = self.query_one(f"#{contact_id}", ListItem)

            # Get fresh contact data from memory
            contact = self.connection.get_contact_by_name(contact_name)
            if not contact:
                return

            contact_type = contact.get("type", 0)
            unread = self.connection.get_unread_count(contact_name)

            # Get fresh last_seen from database (it's updated when messages arrive)
            db_contact = self.connection.db.get_contact_by_name(contact_name)
            last_seen = (
                db_contact.get("last_seen", 0)
                if db_contact
                else contact.get("last_seen", 0)
            )

            # Calculate freshness color
            import time

            age_seconds = time.time() - last_seen if last_seen > 0 else 999999
            if age_seconds < 300:  # 5 minutes
                color = "green"
            elif age_seconds < 3600:  # 1 hour
                color = "yellow"
            else:
                color = "red"

            # Format display
            type_icon = "🏠" if contact_type == 3 else ""
            if unread > 0:
                display_text = (
                    f"[{color}]●[/{color}] {type_icon}{contact_name} ({unread})"
                )
            else:
                display_text = f"[{color}]○[/{color}] {type_icon}{contact_name}"

            # Update the Static widget inside the ListItem
            static = list_item.query_one(Static)
            static.update(display_text)
            self.logger.debug(
                f"Updated contact display for {contact_name}: unread={unread}"
            )
        except Exception as e:
            self.logger.debug(
                f"Could not update contact display for {contact_name}: {e}"
            )

    def _update_single_channel_display(self, channel_name: str) -> None:
        """Update the display of a single channel in the list to reflect new unread count.

        Args:
            channel_name: Name of the channel to update (e.g., "Public", "Channel 1")
        """
        try:
            # Find the channel's ListItem widget
            channel_id = f"channel-{sanitize_id(channel_name)}"
            list_item = self.query_one(f"#{channel_id}", ListItem)

            # Get unread count
            unread = self.connection.get_unread_count(channel_name)

            # Format display
            if unread > 0:
                display_text = f"{channel_name} ({unread})"
            else:
                display_text = channel_name

            # Update the Static widget inside the ListItem
            static = list_item.query_one(Static)
            static.update(display_text)
            self.logger.debug(
                f"Updated channel display for {channel_name}: unread={unread}"
            )
        except Exception as e:
            self.logger.debug(
                f"Could not update channel display for {channel_name}: {e}"
            )

    async def auto_connect(self) -> None:
        """Attempt to auto-connect to a meshcore device."""
        import asyncio

        try:
            self.logger.info("Attempting auto-connect...")
            self.logger.debug(
                f"Args: serial={self.args.serial}, tcp={self.args.tcp}, address={self.args.address}, baudrate={self.args.baudrate}"
            )

            # Check command line arguments for specific connection type
            if self.args.serial:
                self.logger.info(
                    f"Connecting to specified serial device: {self.args.serial}"
                )
                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_serial(
                            port=self.args.serial,
                            baudrate=self.args.baudrate,
                            verify_meshcore=False,
                        ),
                        timeout=15.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.error("Timeout connecting to specified serial device")
                    success = False
                if success:
                    self.logger.info("Connected via serial successfully")
                    self.logger.debug("About to update contacts in UI...")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    self.logger.debug("About to update channels in UI...")
                    await asyncio.wait_for(self.update_channels(), timeout=5.0)
                    self.logger.debug("About to refresh messages...")
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                else:
                    self.logger.error(
                        f"Failed to connect to specified serial device: {self.args.serial}"
                    )
                return  # Don't try auto-detection when serial is explicitly specified

            elif self.args.tcp:
                self.logger.info(
                    f"Connecting to TCP device: {self.args.tcp}:{self.args.port}"
                )
                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_tcp(
                            hostname=self.args.tcp, port=self.args.port
                        ),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.error("Timeout connecting to TCP device")
                    success = False
                if success:
                    self.logger.info("Connected via TCP successfully")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    await asyncio.wait_for(self.update_channels(), timeout=5.0)
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                else:
                    self.logger.error(
                        f"Failed to connect to specified TCP device: {self.args.tcp}:{self.args.port}"
                    )
                return  # Don't try auto-detection when TCP is explicitly specified

            elif self.args.address:
                self.logger.info(f"Connecting to BLE device: {self.args.address}")
                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_ble(address=self.args.address),
                        timeout=15.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.error("Timeout connecting to BLE device")
                    success = False
                if success:
                    self.logger.info("Connected via BLE successfully")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    await asyncio.wait_for(self.update_channels(), timeout=5.0)
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                else:
                    self.logger.error(
                        f"Failed to connect to specified BLE device: {self.args.address}"
                    )
                return  # Don't try auto-detection when BLE address is explicitly specified

            # Fall back to auto-detection if no args provided
            self.logger.info(
                "No connection args provided, attempting auto-detection..."
            )

            # First try serial devices with quick scan (prioritizes USB devices - faster and more reliable)
            self.logger.info("Scanning for serial devices...")
            try:
                serial_devices = await asyncio.wait_for(
                    self.connection.scan_serial_devices(quick_scan=True), timeout=20.0
                )
            except asyncio.TimeoutError:
                self.logger.error("Timeout scanning serial devices")
                serial_devices = []
            if serial_devices:
                # Find first MeshCore device (quick_scan already prioritized USB devices)
                meshcore_device = next(
                    (d for d in serial_devices if d.get("is_meshcore", False)), None
                )
                if not meshcore_device:
                    # Fall back to first device if none identified as MeshCore
                    meshcore_device = serial_devices[0]

                device_to_try = meshcore_device["device"]
                self.logger.info(f"Attempting to connect to: {device_to_try}")

                try:
                    success = await asyncio.wait_for(
                        self.connection.connect_serial(port=device_to_try), timeout=10.0
                    )
                except asyncio.TimeoutError:
                    self.logger.error(
                        f"Timeout connecting to serial device {device_to_try}"
                    )
                    success = False
                if success:
                    self.logger.info("Auto-connected via serial successfully")
                    self.logger.debug("About to update contacts in UI...")
                    await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                    self.logger.debug("About to update channels in UI...")
                    await asyncio.wait_for(self.update_channels(), timeout=5.0)
                    self.logger.debug("About to refresh messages...")
                    await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                    return

            # If serial fails, try BLE connection as fallback
            self.logger.info("Serial auto-connect failed, trying BLE...")
            try:
                success = await asyncio.wait_for(
                    self.connection.connect_ble(), timeout=15.0
                )
            except asyncio.TimeoutError:
                self.logger.error("Timeout auto-connecting via BLE")
                success = False
            if success:
                self.logger.info("Auto-connected via BLE successfully")
                await asyncio.wait_for(self.update_contacts(), timeout=5.0)
                await asyncio.wait_for(self.update_channels(), timeout=5.0)
                await asyncio.wait_for(self.refresh_messages(), timeout=5.0)
                return

            self.logger.info("Auto-connect failed - no compatible devices found")
        except Exception as e:
            self.logger.error(f"Auto-connect failed: {e}")

    @on(Button.Pressed, "#advert-0hop-btn")
    async def send_zero_hop_advert(self) -> None:
        """Send a zero-hop advertisement (only to direct neighbors)."""
        self.logger.info("Sending 0-hop advertisement...")
        try:
            if not self.connection.is_connected():
                self.logger.warning("Not connected to device")
                return

            success = await self.connection.send_advertisement(hops=0)
            if success:
                self.logger.info("✓ Sent 0-hop advertisement successfully")
            else:
                self.logger.error("✗ Failed to send 0-hop advertisement")
        except Exception as e:
            self.logger.error(f"Error sending 0-hop advertisement: {e}")
            import traceback

            self.logger.debug(traceback.format_exc())

    @on(Button.Pressed, "#advert-flood-btn")
    async def send_flood_advert(self) -> None:
        """Send a flooding advertisement (max hops, reaches entire network)."""
        self.logger.info("Sending flood advertisement...")
        try:
            if not self.connection.is_connected():
                self.logger.warning("Not connected to device")
                return

            success = await self.connection.send_advertisement(hops=3)
            if success:
                self.logger.info("✓ Sent flood advertisement successfully (3 hops)")
            else:
                self.logger.error("✗ Failed to send flood advertisement")
        except Exception as e:
            self.logger.error(f"Error sending flood advertisement: {e}")
            import traceback

            self.logger.debug(traceback.format_exc())

    @on(Button.Pressed, "#create-channel-btn")
    def show_create_channel_dialog(self) -> None:
        """Show dialog to create a new channel."""
        from textual.widgets import Label
        from textual.containers import Horizontal, Vertical
        from textual.screen import ModalScreen

        class CreateChannelScreen(ModalScreen):
            """Modal for creating a new channel."""

            def compose(self):
                with Vertical(id="create-channel-dialog"):
                    yield Static("[bold cyan]Create New Channel[/bold cyan]")
                    yield Static(
                        "Channel slot 0 is reserved for Public channel",
                        classes="help-text",
                    )
                    yield Static(
                        "Use # prefix (e.g., #mychannel) for auto-generated secret",
                        classes="help-text",
                    )
                    yield Label("Channel Slot (1-7):")
                    yield Input(placeholder="1", id="channel-slot-input")
                    yield Label("Channel Name:")
                    yield Input(
                        placeholder="#mychannel or Custom Name", id="channel-name-input"
                    )
                    with Horizontal(id="dialog-buttons"):
                        yield Button("Create", id="create-btn", variant="success")
                        yield Button("Cancel", id="cancel-btn", variant="default")

            @on(Button.Pressed, "#create-btn")
            async def create_channel(self):
                """Create the channel."""
                slot_input = self.query_one("#channel-slot-input", Input)
                name_input = self.query_one("#channel-name-input", Input)

                try:
                    slot_str = slot_input.value.strip()
                    name = name_input.value.strip()

                    # Validate inputs
                    if not slot_str:
                        self.app.logger.error("Channel slot is required")
                        self.dismiss()
                        return

                    if not name:
                        self.app.logger.error("Channel name is required")
                        self.dismiss()
                        return

                    # Parse slot number
                    try:
                        slot = int(slot_str)
                    except ValueError:
                        self.app.logger.error(
                            f"Invalid channel slot: '{slot_str}' - must be a number"
                        )
                        self.dismiss()
                        return

                    if slot < 1 or slot > 7:
                        self.app.logger.error(
                            f"Channel slot must be between 1 and 7, got {slot}"
                        )
                        self.dismiss()
                        return

                    success = await self.app.connection.create_channel(slot, name)
                    if success:
                        self.app.logger.info(f"✓ Created channel {slot}: {name}")
                        # Refresh channels list
                        await self.app.update_channels()
                    else:
                        self.app.logger.error(
                            f"✗ Failed to create channel {slot}: {name}"
                        )

                except Exception as e:
                    self.app.logger.error(f"Error creating channel: {e}")
                    import traceback

                    self.app.logger.debug(traceback.format_exc())

                self.dismiss()

            @on(Button.Pressed, "#cancel-btn")
            def cancel(self):
                """Cancel channel creation."""
                self.dismiss()

        self.push_screen(CreateChannelScreen())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks to trigger immediately without requiring focus first."""
        # This allows single-click activation of buttons even when they don't have focus
        pass

    @on(Button.Pressed, "#scan-ble-btn")
    async def show_ble_scanner(self) -> None:
        """Show BLE device scanner dialog."""
        from textual.widgets import Label
        from textual.containers import Horizontal
        from textual.screen import ModalScreen

        class BLEScannerScreen(ModalScreen):
            """Modal for scanning and selecting BLE devices."""

            def compose(self):
                with VerticalScroll(id="ble-scanner-dialog"):
                    yield Static("[bold cyan]BLE Device Connection[/bold cyan]")
                    yield Static(
                        "Scan for new devices or enter address of paired device",
                        classes="help-text",
                    )

                    yield Label("Known Device Address (if already paired):")
                    yield Input(
                        placeholder="E1:C7:FD:AB:2B:DB or leave blank to scan",
                        id="ble-address-input",
                    )

                    yield Static("Or scan for devices:", classes="section-label")
                    yield Static("Scanning for MeshCore devices...", id="scan-status")
                    yield ListView(id="ble-devices-list")

                    yield Label("BLE PIN:")
                    yield Static(
                        "Required for first connection, optional if already paired",
                        classes="help-text",
                    )
                    yield Input(
                        placeholder="Enter PIN from device screen (or leave blank if paired)",
                        id="ble-pin-input",
                        password=False,
                    )
                    with Horizontal(id="dialog-buttons"):
                        yield Button(
                            "Connect", id="connect-addr-btn", variant="success"
                        )
                        yield Button("Rescan", id="rescan-btn", variant="primary")
                        yield Button("Close", id="close-scan-btn", variant="default")

            def on_mount(self):
                """Load saved address and schedule background scan."""
                # Try to load saved BLE address
                saved_address = self.app.connection.ble_transport.get_saved_address()
                if saved_address:
                    address_input = self.query_one("#ble-address-input", Input)
                    address_input.value = saved_address
                    self.query_one("#scan-status", Static).update(
                        f"Last connected: {saved_address}. Click Connect or Rescan."
                    )
                else:
                    # Schedule scan in background so dialog shows immediately
                    self.call_later(self.scan_devices)

            async def scan_devices(self):
                """Scan for BLE devices and populate list."""
                status = self.query_one("#scan-status", Static)
                devices_list = self.query_one("#ble-devices-list", ListView)

                try:
                    status.update("Scanning for MeshCore BLE devices... (5s)")
                    devices_list.clear()

                    # Scan for devices using the BLE transport
                    devices = await self.app.connection.ble_transport.scan_devices(
                        timeout=5.0
                    )

                    if devices:
                        status.update(
                            f"Found {len(devices)} MeshCore device(s). Click to connect:"
                        )
                        for device in devices:
                            name = device.get("name", "Unknown")
                            address = device.get("address", "Unknown")
                            rssi = device.get("rssi", "Unknown")

                            # Create a list item with device info
                            device_text = f"{name}\n  {address} (RSSI: {rssi})"
                            # Sanitize address for ID (remove colons and special chars)
                            safe_id = f"ble-{address.replace(':', '-')}"
                            item = ListItem(Static(device_text), id=safe_id)
                            item.device_address = address  # Store address for later
                            devices_list.append(item)
                    else:
                        status.update("No MeshCore BLE devices found. Try Rescan.")

                except Exception as e:
                    self.app.logger.error(f"Error scanning BLE devices: {e}")
                    status.update(f"Error scanning: {e}")

            @on(ListView.Selected, "#ble-devices-list")
            async def connect_to_device(self, event: ListView.Selected):
                """Connect to selected BLE device."""
                if event.item and hasattr(event.item, "device_address"):
                    address = event.item.device_address
                    pin_input = self.query_one("#ble-pin-input", Input)
                    pin = pin_input.value.strip()

                    if not pin:
                        status = self.query_one("#scan-status", Static)
                        status.update(
                            "[red]Please enter the PIN shown on the device screen[/red]"
                        )
                        return

                    self.app.logger.info(
                        f"Connecting to BLE device: {address} with PIN"
                    )

                    status = self.query_one("#scan-status", Static)
                    status.update(f"Connecting to {address} with PIN...")

                    # Disconnect if already connected
                    if self.app.connection.is_connected():
                        await self.app.connection.disconnect()

                    # Connect to selected device with PIN
                    success = await self.app.connection.connect_ble(
                        address=address, pin=pin
                    )

                    if success:
                        self.app.logger.info(f"✓ Connected to {address}")
                        status.update("✓ Connected, discovering nodes...")
                        # Send advertisement to discover other nodes
                        await self.app.connection.send_advertisement(hops=3)
                        # Update UI
                        await self.app.update_contacts()
                        await self.app.update_channels()
                        status.update(f"✓ Connected to {address}")
                        # Close dialog after successful connection
                        await asyncio.sleep(1)
                        self.dismiss()
                    else:
                        self.app.logger.error(f"✗ Failed to connect to {address}")
                        status.update("✗ Connection failed. Check PIN and try again.")

            @on(Button.Pressed, "#rescan-btn")
            async def rescan(self):
                """Rescan for BLE devices."""
                await self.scan_devices()

            @on(Button.Pressed, "#connect-addr-btn")
            async def connect_by_address(self):
                """Connect to a device by address."""
                address_input = self.query_one("#ble-address-input", Input)
                pin_input = self.query_one("#ble-pin-input", Input)
                status = self.query_one("#scan-status", Static)

                address = address_input.value.strip()
                pin = pin_input.value.strip() or None  # None if empty

                if not address:
                    status.update(
                        "[red]Please enter a BLE address or scan for devices[/red]"
                    )
                    return

                self.app.logger.info(
                    f"Connecting to BLE address: {address}"
                    + (" with PIN" if pin else " (no PIN)")
                )
                status.update(f"Connecting to {address}...")

                # Disconnect if already connected
                if self.app.connection.is_connected():
                    await self.app.connection.disconnect()

                # Connect to specified address
                success = await self.app.connection.connect_ble(
                    address=address, pin=pin
                )

                if success:
                    self.app.logger.info(f"✓ Connected to {address}")
                    status.update(f"✓ Connected to {address}")
                    # Update UI
                    await self.app.update_contacts()
                    await self.app.update_channels()
                    # Close dialog after successful connection
                    await asyncio.sleep(1)
                    self.dismiss()
                else:
                    self.app.logger.error(f"✗ Failed to connect to {address}")
                    status.update(
                        "✗ Connection failed. Check address/PIN and try again."
                    )

            @on(Button.Pressed, "#close-scan-btn")
            def close_scanner(self):
                """Close the scanner dialog."""
                self.dismiss()

            def on_key(self, event):
                """Close dialog on Escape key."""
                if event.key == "escape":
                    self.dismiss()

        self.push_screen(BLEScannerScreen())

    @on(Button.Pressed, "#send-btn")
    async def send_message(self) -> None:
        """Send a message or command."""
        message = self.message_input.value.strip()
        if not message:
            return

        if not self.connection.is_connected():
            self.chat_area.write("[red]Not connected to any device[/red]")
            return

        try:
            if self.current_contact:
                # Check if we're waiting for room password
                if self._awaiting_room_password:
                    # This is a password input for room login
                    self.chat_area.write("[dim]Logging in...[/dim]")
                    success = await self.connection.login_to_room(
                        self.current_contact, message
                    )
                    if success:
                        self.chat_area.write("[green]✓ Logged in successfully![/green]")
                        self.chat_area.write("[dim]Loading queued messages...[/dim]")
                        self._awaiting_room_password = False
                        # Restore normal input mode
                        self.message_input.password = False
                        self.message_input.placeholder = "Type a message..."
                        self.message_input.value = ""
                        # Reload the contact messages (now includes room messages)
                        await self.load_contact_messages(self.current_contact)
                        self.chat_area.write("[dim]Ready to chat![/dim]")
                    else:
                        self.chat_area.write("[red]✗ Login failed. Try again.[/red]")
                        # Keep password mode on for retry
                    self.message_input.value = ""
                    return

                # Sending to a contact (direct message)
                from datetime import datetime

                timestamp = datetime.now().strftime("%H:%M:%S")

                # Show the message first
                self.chat_area.write(
                    f"[dim]{timestamp}[/dim] [blue]You → {self.current_contact}:[/blue] {message}"
                )

                # Then send it (status "✓ Sent" will appear after via callback)
                result = await self.connection.send_message(
                    self.current_contact, message
                )

                if result:
                    self.message_input.value = ""
                    # Update contact display to refresh last_seen indicator
                    self._update_single_contact_display(self.current_contact)
                else:
                    self.chat_area.write(
                        f"[dim]{timestamp}[/dim] [red]✗ Failed to send[/red]"
                    )
            elif self.current_channel:
                # Sending to a channel
                from datetime import datetime

                timestamp = datetime.now().strftime("%H:%M:%S")

                # Extract channel index from "Channel X" format
                if self.current_channel == "Public":
                    channel_name = "Public"
                    channel_id = 0
                else:
                    channel_name = self.current_channel
                    # Extract index from "Channel 1" format
                    try:
                        channel_id = int(channel_name.split()[-1])
                    except (ValueError, IndexError):
                        self.logger.error(f"Invalid channel format: {channel_name}")
                        self.chat_area.write(
                            f"[dim]{timestamp}[/dim] [red]✗ Invalid channel[/red]"
                        )
                        return

                # Show the message first
                self.chat_area.write(
                    f"[dim]{timestamp}[/dim] [cyan]You → {channel_name}:[/cyan] {message}"
                )

                # Then send it (status "✓ Sent" will appear after via callback)
                success = await self.connection.send_channel_message(
                    channel_id, message
                )

                if success:
                    self.message_input.value = ""
                else:
                    self.chat_area.write(
                        f"[dim]{timestamp}[/dim] [red]✗ Failed to send channel message[/red]"
                    )
            else:
                self.chat_area.write(
                    "[yellow]No contact or channel selected. Click a contact or channel to start chatting.[/yellow]"
                )
        except Exception as e:
            self.chat_area.write(f"[red]Error sending message: {e}[/red]")

    @on(Input.Submitted, "#message-input")
    async def on_message_submit(self) -> None:
        """Handle message input submission."""
        await self.send_message()

    @on(Button.Pressed, "#ping-btn")
    async def ping_contact(self) -> None:
        """Test connectivity to contact using path discovery for RTT measurement."""
        if not self.current_contact:
            self.chat_area.write(
                "[yellow]No contact selected. Select a contact first.[/yellow]"
            )
            return

        if not self.connection or not self.connection.is_connected:
            self.chat_area.write("[red]Not connected to device[/red]")
            return

        self.chat_area.write(f"[dim]Testing connectivity to {self.current_contact}...[/dim]")

        try:
            # Use path discovery which includes RTT measurement
            # This is more reliable than send_statusreq
            result = await self.connection.trace_path_to_contact(self.current_contact)

            if result["success"]:
                is_cached = result.get("cached", False)
                path = result.get("path", [])
                hop_count = len(path)

                if is_cached:
                    # Show cached path info without RTT
                    if hop_count == 0:
                        self.chat_area.write(
                            f"[green]✓ {self.current_contact} - Direct connection (cached)[/green]"
                        )
                    else:
                        self.chat_area.write(
                            f"[green]✓ {self.current_contact} reachable via {hop_count} hop{'s' if hop_count > 1 else ''}[/green]"
                        )
                        path_str = " → ".join(path)
                        self.chat_area.write(f"[dim]Path: {path_str}[/dim]")
                else:
                    # Fresh discovery with RTT
                    latency_ms = result.get("latency", 0) * 1000
                    if hop_count == 0:
                        self.chat_area.write(
                            f"[green]✓ {self.current_contact} is reachable! RTT: {latency_ms:.0f}ms (direct)[/green]"
                        )
                    else:
                        self.chat_area.write(
                            f"[green]✓ {self.current_contact} is reachable! RTT: {latency_ms:.0f}ms ({hop_count} hop{'s' if hop_count > 1 else ''})[/green]"
                        )
                        path_str = " → ".join(path)
                        self.chat_area.write(f"[dim]Path: {path_str}[/dim]")
            else:
                error = result.get("error", "Unknown error")
                self.chat_area.write(f"[red]✗ Connectivity test failed: {error}[/red]")
                self.chat_area.write(
                    "[yellow]Contact may be out of range or offline[/yellow]"
                )

        except Exception as e:
            self.chat_area.write(f"[red]Error testing connectivity: {e}[/red]")
            self.logger.error(f"Error in ping handler: {e}")
            import traceback

            self.logger.debug(traceback.format_exc())

    @on(Button.Pressed, "#trace-path-btn")
    async def trace_path_to_contact(self) -> None:
        """Trace the routing path to the currently selected contact."""
        if not self.current_contact:
            self.contact_path_display.update(
                "[yellow]No contact selected[/yellow]"
            )
            return

        if not self.connection or not self.connection.is_connected:
            self.contact_path_display.update("[red]Not connected to device[/red]")
            return

        # Show in-progress indicator
        self.contact_path_display.update(f"[dim]Tracing path to {self.current_contact}...[/dim]")

        try:
            result = await self.connection.trace_path_to_contact(self.current_contact)

            if result["success"]:
                path = result.get("path", [])
                hop_count = len(path)
                is_cached = result.get("cached", False)

                if hop_count == 0:
                    # Direct connection
                    display_text = f"[green]✓ Direct connection[/green]"
                else:
                    # Path through repeaters
                    path_str = " → ".join([f"[cyan]{hop}[/cyan]" for hop in path])
                    display_text = f"[green]✓ {hop_count} hop{'s' if hop_count > 1 else ''}:[/green] {path_str} → [cyan]{self.current_contact}[/cyan]"

                # Add latency if available (only for fresh discovery)
                if result.get("latency"):
                    latency_ms = result["latency"] * 1000
                    display_text += f"\n[dim]Round-trip: {latency_ms:.0f}ms[/dim]"

                # Indicate if cached
                if is_cached:
                    display_text += f"\n[dim](Last known path)[/dim]"
                else:
                    display_text += f"\n[dim](Freshly discovered)[/dim]"

                self.contact_path_display.update(display_text)

                # Also log to chat area for history
                self.chat_area.write(f"[dim]Path {'retrieved' if is_cached else 'traced'} for {self.current_contact}[/dim]")
            else:
                error = result.get("error", "Unknown error")
                self.contact_path_display.update(
                    f"[red]✗ Trace failed:[/red] {error}\n"
                    "[yellow]Contact may be out of range or path discovery failed[/yellow]"
                )

        except Exception as e:
            self.contact_path_display.update(f"[red]Error: {e}[/red]")
            self.logger.error(f"Error in trace path handler: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

    @on(Button.Pressed, "#delete-contact-btn")
    async def delete_contact(self) -> None:
        """Delete the currently selected contact from the device."""
        if not self.current_contact:
            self.chat_area.write(
                "[yellow]No contact selected. Select a contact first.[/yellow]"
            )
            return

        if not self.connection or not self.connection.is_connected:
            self.chat_area.write("[red]Not connected to device[/red]")
            return

        # Store contact name before deletion
        contact_name = self.current_contact

        # Confirm deletion
        self.chat_area.write(
            f"[yellow]⚠ Deleting contact '{contact_name}' from device...[/yellow]"
        )

        try:
            success = await self.connection.remove_contact(contact_name)

            if success:
                self.chat_area.write(
                    f"[green]✓ Contact '{contact_name}' removed successfully[/green]"
                )
                self.chat_area.write("[dim]The contact list has been refreshed.[/dim]")

                # Clear selection and chat area
                self.current_contact = None
                self.current_contact_pubkey = None
                self.chat_area.clear()

                # Update the UI to reflect the deleted contact
                await self.update_contacts()
            else:
                self.chat_area.write(
                    f"[red]✗ Failed to remove contact '{contact_name}'[/red]"
                )

        except Exception as e:
            self.chat_area.write(f"[red]Error deleting contact: {e}[/red]")
            self.logger.error(f"Error in delete contact handler: {e}")
            import traceback

            self.logger.debug(traceback.format_exc())

    @on(ListView.Selected, "#contacts-list")
    async def on_contact_selected(self, event: ListView.Selected) -> None:
        """Handle contact selection."""
        if event.item and event.item.id:
            # Look up the contact name from the ID mapping
            self.logger.debug(
                f"🔍 Contact selected: item.id={event.item.id}, id_map={self._contact_id_map}"
            )
            contact_name = self._contact_id_map.get(event.item.id)
            if not contact_name:
                self.logger.warning(f"No contact found for ID: {event.item.id}")
                return

            self.logger.info(
                f"Selected contact: {contact_name} (from ID: {event.item.id})"
            )

            # Get the contact to extract public_key for reliable lookups
            contact = self.connection.get_contact_by_name(contact_name)
            if not contact:
                self.logger.warning(f"Contact not found: {contact_name}")
                return

            pubkey = contact.get("public_key")
            if not pubkey:
                self.logger.warning(f"Contact {contact_name} has no public_key")
                return

            self.logger.debug(f"Contact selected: {contact_name}, pubkey: {pubkey[:16]}..., type: {contact.get('type')}")

            # Set both name (for compatibility) and public_key (canonical identifier)
            self.current_contact = contact_name
            self.current_contact_pubkey = pubkey
            self.current_channel = None  # Clear channel selection

            # Show Contact Info tab for contacts (has relevant metadata)
            self.tabbed_content.show_tab("contact-info-tab")

            # Update Contact Info tab with contact public_key
            self.logger.debug(f"Calling load_contact_info with pubkey: {pubkey[:16]}...")
            self.load_contact_info(pubkey)

            # Mark messages as read and update display
            self.connection.mark_as_read(contact_name)
            self._update_single_contact_display(contact_name)

            # Check if this is a room server (type 3) and prompt for password if needed
            if contact and contact.get("type") == 3:
                # This is a room server - check if we're logged in
                if not self.connection.is_logged_into_room(contact_name):
                    self.chat_area.clear()
                    self.chat_area.write(
                        f"[bold cyan]{contact_name} (Room Server)[/bold cyan]"
                    )
                    self.chat_area.write(
                        "[yellow]This is a room server. You need to login first.[/yellow]"
                    )
                    self.chat_area.write(
                        "[dim]Type password in the input field below and press Enter to login.[/dim]"
                    )
                    self.logger.info(
                        f"{contact_name} is a room server, waiting for password"
                    )
                    # Set a flag to indicate we're waiting for password
                    self._awaiting_room_password = True
                    # Enable password mode on message input
                    self.message_input.password = True
                    self.message_input.placeholder = "Enter room password..."
                    self.message_input.focus()
                    return

            # Regular contact or already logged in
            self._awaiting_room_password = False
            # Disable password mode
            self.message_input.password = False
            self.message_input.placeholder = "Type a message..."

            # Update chat area header
            # Clear the chat area completely
            self.chat_area.clear()
            self.chat_area.lines.clear()  # Also clear internal lines buffer

            if contact and contact.get("type") == 3:
                self.chat_area.write(
                    f"[bold cyan]Chat with {contact_name} (Room Server)[/bold cyan]\n"
                )
            elif contact and contact.get("type") == 2:
                self.chat_area.write(
                    f"[bold cyan]Chat with {contact_name} (Repeater)[/bold cyan]\n"
                )
            else:
                self.chat_area.write(
                    f"[bold cyan]Chat with {contact_name}[/bold cyan]\n"
                )

            # Force refresh to ensure UI updates
            self.chat_area.refresh()

            # Load message history for this contact
            await self.load_contact_messages(contact_name)

            # Load contact info for Contact Info tab (using public_key if available)
            if pubkey:
                self.load_contact_info(pubkey)

            # Focus the message input
            self.message_input.focus()

    @on(ListView.Selected, "#channels-list")
    async def on_channel_selected(self, event: ListView.Selected) -> None:
        """Handle channel selection."""
        if event.item and event.item.id:
            # Look up the channel name from the ID mapping
            channel_name = self._channel_id_map.get(event.item.id)
            if not channel_name:
                self.logger.warning(f"No channel found for ID: {event.item.id}")
                return

            self.current_channel = channel_name
            self.current_contact = None  # Clear contact selection
            self.current_contact_pubkey = None  # Clear contact pubkey
            self.logger.info(f"Selected channel: {channel_name}")

            # Hide Contact Info tab since channels don't have contact metadata
            self.tabbed_content.hide_tab("contact-info-tab")

            # Mark channel messages as read and update display
            self.connection.mark_as_read(channel_name)
            self._update_single_channel_display(channel_name)

            # Update chat area header
            self.chat_area.clear()

            # Show last seen for contacts
            contact = self.connection.get_contact_by_name(channel_name)
            if contact:
                last_seen = contact.get("last_seen", 0)
                if last_seen > 0:
                    import time

                    age_seconds = time.time() - last_seen

                    if age_seconds < 60:
                        last_seen_str = "just now"
                    elif age_seconds < 3600:
                        last_seen_str = f"{int(age_seconds / 60)} min ago"
                    elif age_seconds < 86400:
                        last_seen_str = f"{int(age_seconds / 3600)} hr ago"
                    else:
                        last_seen_str = f"{int(age_seconds / 86400)} days ago"

                    self.chat_area.write(
                        f"[bold cyan]{channel_name}[/bold cyan] [dim](last seen: {last_seen_str})[/dim]\n"
                    )
                else:
                    self.chat_area.write(f"[bold cyan]{channel_name}[/bold cyan]\n")
            elif channel_name == "Public":
                self.chat_area.write(
                    "[bold cyan]Public Channel (All Messages)[/bold cyan]\n"
                )
            else:
                self.chat_area.write(
                    f"[bold cyan]Channel: {channel_name}[/bold cyan]\n"
                )

            # Load message history for this channel
            await self.load_channel_messages(channel_name)

            # Focus the message input
            self.message_input.focus()

    def action_refresh(self) -> None:
        """Refresh the current view."""
        self.logger.info("Refreshing...")

    def action_help(self) -> None:
        """Show help information."""
        self.logger.info("Showing help...")

    async def load_contact_messages(self, contact_name: str) -> None:
        """Load and display message history for a contact."""
        try:
            self.logger.debug(f"Loading messages for contact: {contact_name}")
            messages = self.connection.get_messages_for_contact(contact_name)
            self.logger.debug(f"Retrieved {len(messages)} messages for {contact_name}")
            if messages:
                from datetime import datetime

                for msg in messages:
                    timestamp = msg.get("timestamp", 0)
                    if timestamp and timestamp > 0:
                        try:
                            # Handle both ISO format and unix timestamp
                            if isinstance(timestamp, str):
                                dt = datetime.fromisoformat(timestamp)
                            else:
                                dt = datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%H:%M:%S")
                            self.logger.debug(f"Timestamp {timestamp} -> {time_str}")
                        except Exception as e:
                            self.logger.error(
                                f"Failed to format timestamp {timestamp}: {e}"
                            )
                            time_str = str(timestamp)
                    else:
                        time_str = "--:--:--"
                        self.logger.debug(
                            f"No timestamp for message: {msg.get('text', '')[:20]}"
                        )

                    sender = msg.get("sender", "Unknown")
                    sender_pubkey = msg.get("sender_pubkey", "")
                    actual_sender = msg.get("actual_sender")  # For room messages
                    actual_sender_pubkey = msg.get("actual_sender_pubkey", "")
                    msg_type = msg.get("type", "contact")
                    text = msg.get("text", "")
                    signature = msg.get("signature", "")

                    # Check if this message is from me by comparing pubkeys
                    is_from_me = False
                    my_contact = (
                        self.connection.db.get_contact_by_me()
                        if self.connection
                        else None
                    )
                    if my_contact:
                        my_pubkey = my_contact.get("public_key")
                        if my_pubkey:
                            # Check if any of the sender fields match our pubkey (prefix or full)
                            if sender_pubkey and (
                                sender_pubkey == my_pubkey
                                or my_pubkey.startswith(sender_pubkey)
                            ):
                                is_from_me = True
                            elif actual_sender_pubkey and (
                                actual_sender_pubkey == my_pubkey
                                or my_pubkey.startswith(actual_sender_pubkey)
                            ):
                                is_from_me = True
                            elif signature and (
                                signature == my_pubkey
                                or my_pubkey.startswith(signature)
                            ):
                                is_from_me = True
                    elif sender == "Me":
                        is_from_me = True

                    # Check if sender is a room server (type 3)
                    sender_contact = self.connection.get_contact_by_name(sender)
                    is_room_server = sender_contact and sender_contact.get("type") == 3

                    # If no actual_sender but we have a signature, try to decode it
                    if is_room_server and not actual_sender and signature:
                        sig_contact = (
                            self.connection.contacts.get_by_key(signature)
                            if self.connection.contacts
                            else None
                        )
                        if sig_contact:
                            actual_sender = sig_contact.get(
                                "adv_name"
                            ) or sig_contact.get("name", signature)
                        else:
                            actual_sender = signature[:8]  # Show short key if unknown

                    # Format sender display (same as refresh_messages)
                    if is_from_me:
                        # Message sent by me (based on pubkey) - always show as "You"
                        self.chat_area.write(
                            f"[dim]{time_str}[/dim] [blue]You:[/blue] {text}\n"
                        )
                    elif (msg_type == "room" or is_room_server) and actual_sender:
                        # Room message - show "Room / Sender: message"
                        display_sender = f"{sender} / {actual_sender}"
                        self.chat_area.write(
                            f"[dim]{time_str}[/dim] [cyan]{display_sender}:[/cyan] {text}\n"
                        )
                    elif msg_type == "room" or is_room_server:
                        # Room message without sender info - show as anonymous
                        self.chat_area.write(
                            f"[dim]{time_str}[/dim] [cyan]{sender} / [dim]Anonymous[/dim]:[/cyan] {text}\n"
                        )
                    elif sender == contact_name:
                        self.chat_area.write(
                            f"[dim]{time_str}[/dim] [green]{sender}:[/green] {text}\n"
                        )
                    else:
                        # Show actual sender name (could be someone else in a room conversation)
                        self.chat_area.write(
                            f"[dim]{time_str}[/dim] [green]{sender}:[/green] {text}\n"
                        )
            else:
                self.chat_area.write("[dim]No message history[/dim]")
        except Exception as e:
            self.logger.error(f"Error loading contact messages: {e}")

    async def load_channel_messages(self, channel_name: str) -> None:
        """Load and display message history for a channel."""
        try:
            messages = self.connection.get_messages_for_channel(channel_name)
            if messages:
                from datetime import datetime

                for msg in messages:
                    timestamp = msg.get("timestamp", 0)
                    if timestamp and timestamp > 0:
                        try:
                            # Handle both ISO format and unix timestamp
                            if isinstance(timestamp, str):
                                dt = datetime.fromisoformat(timestamp)
                            else:
                                dt = datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%H:%M:%S")
                        except Exception:
                            time_str = str(timestamp)
                    else:
                        time_str = "--:--:--"

                    sender = msg.get("sender", "Unknown")
                    text = msg.get("text", "")

                    # Show "You" for messages sent by me
                    if sender == "Me":
                        self.chat_area.write(
                            f"[dim]{time_str}[/dim] [blue]You:[/blue] {text}\n"
                        )
                    else:
                        self.chat_area.write(
                            f"[dim]{time_str}[/dim] [yellow]{sender}:[/yellow] {text}\n"
                        )
            else:
                self.chat_area.write("[dim]No message history[/dim]")
        except Exception as e:
            self.logger.error(f"Error loading channel messages: {e}")

    def load_contact_info(self, pubkey: str) -> None:
        """Load contact information into the Contact Info tab.

        Args:
            pubkey: Public key of the contact to load
        """
        try:
            self.logger.debug(f"Loading contact info for pubkey: {pubkey[:16]}...")

            # Look up contact by public_key (not name, as names can change)
            contact = self.connection.db.get_contact_by_pubkey(pubkey)
            if not contact:
                self.logger.warning(f"Contact not found in database for pubkey: {pubkey[:16]}...")
                self.contact_info_status.update("Contact not found")
                return

            self.logger.debug(f"Found contact: {contact.get('name')} (type: {contact.get('type')})")

            # Update contact details
            contact_name = contact.get("name", "Unknown")
            self.contact_name_display.update(contact_name)

            # Display public_key (canonical field name from meshcore API)
            display_pubkey = pubkey[:16] + "..." if len(pubkey) > 16 else pubkey
            self.contact_pubkey_display.update(display_pubkey)

            # Contact type mapping using match/case (Python 3.10+)
            contact_type = contact.get("type", 0)
            match contact_type:
                case 0 | 1:
                    type_name = "Companion"
                case 2:
                    type_name = "Repeater"
                case 3:
                    type_name = "Room Server"
                case 4:
                    type_name = "Sensor"
                case _:
                    type_name = f"Unknown ({contact_type})"
            self.contact_type_display.update(type_name)

            # Display last seen timestamp
            last_seen = contact.get("last_seen", 0)
            if last_seen > 0:
                from datetime import datetime
                last_seen_dt = datetime.fromtimestamp(last_seen)
                # Calculate time difference using match/case (Python 3.10+)
                now = datetime.now()
                diff = now - last_seen_dt

                match (diff.days, diff.seconds):
                    case (days, _) if days > 0:
                        last_seen_str = f"{days} day{'s' if days > 1 else ''} ago"
                    case (_, seconds) if seconds >= 3600:
                        hours = seconds // 3600
                        last_seen_str = f"{hours} hour{'s' if hours > 1 else ''} ago"
                    case (_, seconds) if seconds >= 60:
                        minutes = seconds // 60
                        last_seen_str = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
                    case _:
                        last_seen_str = "Just now"

                self.contact_lastseen_display.update(f"{last_seen_str} ({last_seen_dt.strftime('%Y-%m-%d %H:%M:%S')})")
            else:
                self.contact_lastseen_display.update("Never")

            # Load notes from database using public_key
            notes = self.connection.db.get_contact_notes(pubkey)
            self.contact_notes_input.load_text(notes)

            self.contact_info_status.update(f"Viewing contact: {contact_name}")
        except Exception as e:
            self.logger.error(f"Error loading contact info: {e}")
            self.contact_info_status.update(f"Error loading contact info: {e}")

    @on(Button.Pressed, "#save-notes-btn")
    async def save_contact_notes(self) -> None:
        """Save notes for the current contact using public_key lookup."""
        if not self.current_contact_pubkey:
            self.contact_info_status.update("No contact selected")
            return

        try:
            # Use stored public_key for reliable lookup (names can change)
            notes = self.contact_notes_input.text
            success = self.connection.db.set_contact_notes(self.current_contact_pubkey, notes)

            if success:
                # Get current name for display (may have changed since selection)
                contact = self.connection.db.get_contact_by_pubkey(self.current_contact_pubkey)
                contact_name = contact.get("name", "Unknown") if contact else self.current_contact
                self.contact_info_status.update(f"Notes saved for {contact_name}")
            else:
                self.contact_info_status.update("Failed to save notes")
        except Exception as e:
            self.logger.error(f"Error saving contact notes: {e}")
            self.contact_info_status.update(f"Error: {e}")

    async def update_contacts(self) -> None:
        """Update the contacts list in the UI."""
        import asyncio

        # Prevent concurrent updates
        if hasattr(self, "_updating_contacts") and self._updating_contacts:
            self.logger.debug("Contact update already in progress, skipping")
            return

        self._updating_contacts = True
        try:
            self.logger.debug("Starting contact update process...")

            # Just get the contacts that were already refreshed by the connection
            # Don't call refresh_contacts() again as it may have just been called
            contacts = self.connection.get_contacts()
            self.logger.debug(f"Retrieved {len(contacts)} contacts from connection")

            # First, remove all existing ListItem widgets from the contacts_list
            # This is necessary because clear() doesn't actually remove widgets from DOM
            try:
                for item in list(self.contacts_list.children):
                    if isinstance(item, ListItem):
                        await item.remove()
            except Exception as e:
                self.logger.debug(f"Error removing old items: {e}")

            # Now clear the list and mapping
            self.contacts_list.clear()
            self._contact_id_map.clear()

            for contact in contacts:
                contact_name = contact.get("name", "Unknown")
                contact_type = contact.get("type", 0)

                # Get unread count
                unread = self.connection.get_unread_count(contact_name)

                # Determine freshness color based on last_seen
                last_seen = contact.get("last_seen", 0)
                self.logger.debug(
                    f"🔍 Contact {contact_name}: unread={unread}, last_seen={last_seen}"
                )
                import time

                age_seconds = time.time() - last_seen if last_seen > 0 else 999999

                # Color: green < 5min, yellow < 1hr, red > 1hr
                if age_seconds < 300:  # 5 minutes
                    color = "green"
                elif age_seconds < 3600:  # 1 hour
                    color = "yellow"
                else:
                    color = "red"

                # Format display with unread indicator and freshness
                type_icon = "🏠" if contact_type == 3 else ""  # Room server icon
                if unread > 0:
                    display_text = (
                        f"[{color}]●[/{color}] {type_icon}{contact_name} ({unread})"
                    )
                else:
                    display_text = f"[{color}]○[/{color}] {type_icon}{contact_name}"

                # Create ListItem with sanitized contact name as id for data retrieval
                contact_id = f"contact-{sanitize_id(contact_name)}"
                self._contact_id_map[contact_id] = contact_name  # Store mapping
                list_item = ListItem(Static(display_text, markup=True), id=contact_id)

                self.contacts_list.append(list_item)
                self.logger.debug(f"Added contact to UI: {contact_name}")

            self.logger.info(f"Updated {len(contacts)} contacts in UI")
        except asyncio.TimeoutError:
            self.logger.error("Timeout updating contacts")
        except Exception as e:
            self.logger.error(f"Failed to update contacts: {e}")
            import traceback

            self.logger.debug(f"Contact update traceback: {traceback.format_exc()}")
        finally:
            self._updating_contacts = False

    async def update_channels(self) -> None:
        """Update the channels list in the UI."""

        try:
            self.logger.debug("Starting channel update process...")
            channels = await self.connection.get_channels()  # Await the async method
            self.logger.debug(f"Retrieved {len(channels)} channels from connection")

            # Clear and repopulate channels list
            self.channels_list.clear()
            self._channel_id_map.clear()  # Clear the mapping

            # Always add "Public" as first item with unread count
            public_unread = self.connection.get_unread_count("Public")
            if public_unread > 0:
                public_display = f"Public ({public_unread})"
            else:
                public_display = "Public"
            public_id = "channel-Public"
            self._channel_id_map[public_id] = "Public"
            self.channels_list.append(ListItem(Static(public_display), id=public_id))

            # Add other channels (channels is a list, not dict)
            for channel_info in channels:
                channel_name = channel_info.get("name", "Unknown")
                channel_idx = channel_info.get("channel_idx", 0)
                if channel_name and channel_name != "Public":
                    # Store channel with index for proper message filtering
                    channel_key = f"Channel {channel_idx}"
                    channel_unread = self.connection.get_unread_count(channel_key)

                    if channel_unread > 0:
                        display_text = f"{channel_name} ({channel_unread})"
                    else:
                        display_text = channel_name

                    channel_id = f"channel-{sanitize_id(channel_name)}"
                    # Store the "Channel X" format for database queries
                    self._channel_id_map[channel_id] = channel_key
                    self.channels_list.append(
                        ListItem(Static(display_text), id=channel_id)
                    )
                    self.logger.debug(
                        f"Added channel to UI: {channel_name} (index {channel_idx})"
                    )

            self.logger.info(
                f"Updated {len(channels) + 1} channels in UI (including Public)"
            )
        except Exception as e:
            self.logger.error(f"Failed to update channels: {e}")
            import traceback

            self.logger.debug(f"Channel update traceback: {traceback.format_exc()}")

    async def refresh_messages(self) -> None:
        """Refresh and display messages for the current view."""
        import asyncio

        try:
            self.logger.debug("Refreshing messages...")

            # Clear the chat area
            self.chat_area.clear()

            # Get filtered messages based on current view
            if self.current_contact:
                messages = self.connection.get_messages_for_contact(
                    self.current_contact
                )
                self.logger.debug(
                    f"Retrieved {len(messages)} messages for contact {self.current_contact}"
                )
            elif self.current_channel is not None:
                messages = self.connection.get_messages_for_channel(
                    self.current_channel
                    if isinstance(self.current_channel, str)
                    else "Public"
                )
                self.logger.debug(
                    f"Retrieved {len(messages)} messages for channel {self.current_channel}"
                )
            else:
                # No view selected, show nothing
                messages = []
                self.logger.debug("No contact or channel selected")

            # Display messages
            from datetime import datetime

            for msg in messages:
                # Format timestamp
                timestamp = msg.get("timestamp", 0)
                if timestamp and timestamp > 0:
                    try:
                        if isinstance(timestamp, str):
                            dt = datetime.fromisoformat(timestamp)
                        else:
                            dt = datetime.fromtimestamp(timestamp)
                        time_str = dt.strftime("%H:%M:%S")
                    except Exception as e:
                        self.logger.error(
                            f"Failed to format timestamp {timestamp}: {e}"
                        )
                        time_str = str(timestamp)
                else:
                    time_str = "--:--:--"

                sender = msg.get("sender", "Unknown")
                sender_pubkey = msg.get("sender_pubkey", "")
                content = msg.get("text", "")
                msg_type = msg.get("type", "contact")
                actual_sender = msg.get("actual_sender")  # For room messages
                actual_sender_pubkey = msg.get("actual_sender_pubkey", "")
                signature = msg.get("signature", "")

                # Check if this message is from me by comparing pubkeys
                is_from_me = False
                my_contact = (
                    self.connection.db.get_contact_by_me() if self.connection else None
                )
                if my_contact:
                    my_pubkey = my_contact.get("public_key")
                    if my_pubkey:
                        # Check if any of the sender fields match our pubkey (prefix or full)
                        if sender_pubkey and (
                            sender_pubkey == my_pubkey
                            or my_pubkey.startswith(sender_pubkey)
                        ):
                            is_from_me = True
                        elif actual_sender_pubkey and (
                            actual_sender_pubkey == my_pubkey
                            or my_pubkey.startswith(actual_sender_pubkey)
                        ):
                            is_from_me = True
                        elif signature and (
                            signature == my_pubkey or my_pubkey.startswith(signature)
                        ):
                            is_from_me = True
                elif sender == "Me":
                    is_from_me = True

                # Check if sender is a room server (type 3)
                sender_contact = self.connection.get_contact_by_name(sender)
                is_room_server = sender_contact and sender_contact.get("type") == 3

                # If no actual_sender but we have a signature, try to decode it
                if is_room_server and not actual_sender and signature:
                    sig_contact = (
                        self.connection.contacts.get_by_key(signature)
                        if self.connection.contacts
                        else None
                    )
                    if sig_contact:
                        actual_sender = sig_contact.get("adv_name") or sig_contact.get(
                            "name", signature
                        )
                    else:
                        actual_sender = signature[:8]  # Show short key if unknown

                # Format sender display with timestamps
                if is_from_me:
                    # Message sent by me (based on pubkey) - always show as "You"
                    self.chat_area.write(
                        f"[dim]{time_str}[/dim] [blue]You:[/blue] {content}\n"
                    )
                elif (msg_type == "room" or is_room_server) and actual_sender:
                    display_sender = f"{sender} / {actual_sender}"
                    self.chat_area.write(
                        f"[dim]{time_str}[/dim] [cyan]{display_sender}:[/cyan] {content}\n"
                    )
                elif msg_type == "room" or is_room_server:
                    self.chat_area.write(
                        f"[dim]{time_str}[/dim] [cyan]{sender} / [dim]Anonymous[/dim]:[/dim] {content}\n"
                    )
                elif self.current_contact and sender == self.current_contact:
                    self.chat_area.write(
                        f"[dim]{time_str}[/dim] [green]{sender}:[/green] {content}\n"
                    )
                elif msg_type == "channel":
                    self.chat_area.write(
                        f"[dim]{time_str}[/dim] [yellow]{sender}:[/yellow] {content}\n"
                    )
                else:
                    # Show actual sender name (could be someone else in a room conversation)
                    self.chat_area.write(
                        f"[dim]{time_str}[/dim] [green]{sender}:[/green] {content}\n"
                    )

        except asyncio.TimeoutError:
            self.logger.error("Timeout refreshing messages")
        except Exception as e:
            self.logger.error(f"Failed to refresh messages: {e}")
            import traceback

            self.logger.debug(f"Message refresh traceback: {traceback.format_exc()}")

    async def periodic_message_refresh(self) -> None:
        """Periodically check for and display new messages."""
        if not self.connection.is_connected():
            return

        try:
            # Track the number of messages we've already displayed
            if not hasattr(self, "_displayed_message_count"):
                self._displayed_message_count = 0

            # Get all messages
            all_messages = await self.connection.get_messages()

            # Only display new messages
            new_messages = all_messages[self._displayed_message_count :]

            for msg in new_messages:
                sender = msg.get("sender", "Unknown")
                content = msg.get("text", "")
                msg_type = msg.get("type", "")

                # Filter based on current view
                if self.current_contact:
                    # Show messages from/to this contact (including room messages)
                    if (
                        msg_type == "contact" or msg_type == "room"
                    ) and sender == self.current_contact:
                        self.chat_area.write(f"[green]{sender}:[/green] {content}\n")
                elif self.current_channel is not None:
                    # Show messages from this channel
                    if (
                        msg_type == "channel"
                        and msg.get("channel") == self.current_channel
                    ):
                        self.chat_area.write(f"[cyan]{sender}:[/cyan] {content}\n")

            self._displayed_message_count = len(all_messages)

        except Exception as e:
            self.logger.debug(f"Periodic refresh error: {e}")

    @on(Button.Pressed, "#node-login-btn")
    async def node_login(self) -> None:
        """Log into a repeater node."""
        node_name = self.node_name_input.value.strip()
        password = self.node_password_input.value.strip()

        if not node_name or not password:
            self.node_status_area.write(
                "Please enter both repeater name and password\n"
            )
            return

        self.logger.info(f"Logging into repeater: {node_name}")
        success = await self.connection.login_to_node(node_name, password)

        if success:
            self.node_status_area.write(f"✓ Successfully logged into {node_name}\n")
            self.node_password_input.value = ""  # Clear password
        else:
            self.node_status_area.write(f"✗ Failed to log into {node_name}\n")

    @on(Button.Pressed, "#node-send-cmd-btn")
    async def node_send_command(self) -> None:
        """Send a command to a node (repeater, room server, or sensor)."""
        command = self.node_command_input.value.strip()
        node_name = self.node_cmd_target_input.value.strip()

        # If no node name specified, use current contact from chat
        if not node_name and self.current_contact:
            node_name = self.current_contact

        if not command:
            self.node_status_area.write("Please enter a command\n")
            return

        if not node_name:
            self.node_status_area.write(
                "Please specify target node name or select a contact in Chat tab\n"
            )
            return

        self.logger.info(f"Sending command to {node_name}: {command}")
        success = await self.connection.send_command_to_node(node_name, command)

        if success:
            self.node_status_area.write(f"✓ Sent to {node_name}: {command}\n")
            self.node_command_input.value = ""
        else:
            self.node_status_area.write(f"✗ Failed to send command to {node_name}\n")

    @on(Input.Submitted, "#node-command-input")
    async def node_command_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in command input - same as clicking Send button."""
        # Prevent default behavior
        event.prevent_default()

        self.logger.info("🔍 DEBUG: node-command-input submitted!")
        command = self.node_command_input.value.strip()
        node_name = self.node_cmd_target_input.value.strip()

        self.logger.info(f"🔍 DEBUG: command='{command}', node_name='{node_name}'")

        # If no node name specified, use current contact from chat
        if not node_name and self.current_contact:
            node_name = self.current_contact

        if not command:
            self.node_status_area.write("Please enter a command\n")
            return

        if not node_name:
            self.node_status_area.write(
                "Please specify target node name or select a contact in Chat tab\n"
            )
            return

        self.logger.info(f"Sending command to {node_name}: {command}")
        success = await self.connection.send_command_to_node(node_name, command)

        if success:
            self.node_status_area.write(f"✓ Sent to {node_name}: {command}\n")
            self.node_command_input.value = ""
        else:
            self.node_status_area.write(f"✗ Failed to send command to {node_name}\n")

    @on(Button.Pressed, "#node-status-btn")
    async def node_get_status(self) -> None:
        """Get status from a node."""
        node_name = self.node_status_target_input.value.strip()

        if not node_name:
            self.node_status_area.write("Please specify node name\n")
            return

        self.logger.info(f"Requesting status from {node_name}")
        status = await self.connection.request_node_status(node_name)

        if status:
            import json

            status_json = json.dumps(status, indent=2)
            self.node_status_area.write(f"Status from {node_name}:\n{status_json}\n\n")
        else:
            self.node_status_area.write(f"✗ Failed to get status from {node_name}\n")

    # Device Settings Handlers

    async def populate_device_settings(self) -> None:
        """Populate device settings with current values from connected device."""
        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "Not connected to device. Settings unavailable."
                )
                return

            self.settings_status_area.write("Loading current device settings...")

            # Get device info using appstart command (includes more details than device_query)
            result = await self.connection.meshcore.commands.send_appstart()

            if hasattr(result, "payload") and result.payload:
                info = result.payload

                # Display device name (if available)
                device_name = info.get("name", info.get("long_name", ""))
                if device_name:
                    self.settings_name_input.placeholder = f"Current: {device_name}"

                # Display model and version info
                model = (
                    self.connection.device_info.get("model", "Unknown")
                    if self.connection.device_info
                    else "Unknown"
                )
                version = (
                    self.connection.device_info.get("ver", "Unknown")
                    if self.connection.device_info
                    else "Unknown"
                )

                self.settings_status_area.write(
                    f"[green]Device: {model} ({version})[/green]"
                )

                # Note: Radio parameters (freq, bw, sf, cr) and TX power are not returned by appstart
                # They would need separate commands to query, which MeshCore may not expose
                self.settings_status_area.write(
                    "[dim]Note: Enter new values to update radio settings[/dim]"
                )

            else:
                self.settings_status_area.write(
                    "[yellow]Could not retrieve device settings[/yellow]"
                )

        except Exception as e:
            self.logger.error(f"Error loading device settings: {e}")
            self.settings_status_area.write(f"[red]Error loading settings: {e}[/red]")

    @on(TabbedContent.TabActivated)
    async def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation events."""
        if event.pane.id == "settings-tab":
            # When Device Settings tab is opened, populate current settings
            await self.populate_device_settings()

    @on(Button.Pressed, "#settings-name-btn")
    async def set_device_name(self) -> None:
        """Set the device name."""
        name = self.settings_name_input.value.strip()
        if not name:
            self.settings_status_area.write(
                "[red]Error: Device name cannot be empty[/red]"
            )
            return

        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "[red]Error: Not connected to device[/red]"
                )
                return

            self.settings_status_area.write(f"Setting device name to: {name}")
            result = await self.connection.meshcore.commands.set_name(name)

            if hasattr(result, "type") and "ERROR" in str(result.type):
                self.settings_status_area.write(
                    f"[red]✗ Failed to set name: {result}[/red]"
                )
            else:
                self.settings_status_area.write(
                    f"[green]✓ Device name set to: {name}[/green]"
                )
                self.settings_name_input.value = ""
        except Exception as e:
            self.logger.error(f"Error setting device name: {e}")
            self.settings_status_area.write(f"[red]✗ Error: {e}[/red]")

    @on(Button.Pressed, "#settings-tx-power-btn")
    async def set_tx_power(self) -> None:
        """Set the TX power."""
        try:
            power = int(self.settings_tx_power_input.value.strip())
        except ValueError:
            self.settings_status_area.write(
                "[red]Error: TX power must be a number[/red]"
            )
            return

        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "[red]Error: Not connected to device[/red]"
                )
                return

            self.settings_status_area.write(f"Setting TX power to: {power} dBm")
            result = await self.connection.meshcore.commands.set_tx_power(power)

            if hasattr(result, "type") and "ERROR" in str(result.type):
                self.settings_status_area.write(
                    f"[red]✗ Failed to set TX power: {result}[/red]"
                )
            else:
                self.settings_status_area.write(
                    f"[green]✓ TX power set to: {power} dBm[/green]"
                )
                self.settings_tx_power_input.value = ""
        except Exception as e:
            self.logger.error(f"Error setting TX power: {e}")
            self.settings_status_area.write(f"[red]✗ Error: {e}[/red]")

    @on(Button.Pressed, "#settings-radio-btn")
    async def set_radio_config(self) -> None:
        """Set radio configuration parameters."""
        try:
            freq = float(self.settings_freq_input.value.strip())
            bw = float(self.settings_bw_input.value.strip())
            sf = int(self.settings_sf_input.value.strip())
            cr = int(self.settings_cr_input.value.strip())
        except ValueError:
            self.settings_status_area.write(
                "[red]Error: All radio parameters must be numbers[/red]"
            )
            return

        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "[red]Error: Not connected to device[/red]"
                )
                return

            self.settings_status_area.write(
                f"Setting radio: freq={freq}MHz, bw={bw}kHz, sf={sf}, cr={cr}"
            )
            result = await self.connection.meshcore.commands.set_radio(freq, bw, sf, cr)

            if hasattr(result, "type") and "ERROR" in str(result.type):
                self.settings_status_area.write(
                    f"[red]✗ Failed to set radio config: {result}[/red]"
                )
            else:
                self.settings_status_area.write(
                    "[green]✓ Radio configured successfully[/green]"
                )
                self.settings_freq_input.value = ""
                self.settings_bw_input.value = ""
                self.settings_sf_input.value = ""
                self.settings_cr_input.value = ""
        except Exception as e:
            self.logger.error(f"Error setting radio config: {e}")
            self.settings_status_area.write(f"[red]✗ Error: {e}[/red]")

    @on(Button.Pressed, "#settings-coords-btn")
    async def set_coordinates(self) -> None:
        """Set device coordinates."""
        try:
            lat = float(self.settings_lat_input.value.strip())
            lon = float(self.settings_lon_input.value.strip())
        except ValueError:
            self.settings_status_area.write(
                "[red]Error: Latitude and longitude must be numbers[/red]"
            )
            return

        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "[red]Error: Not connected to device[/red]"
                )
                return

            self.settings_status_area.write(
                f"Setting coordinates: lat={lat}, lon={lon}"
            )
            result = await self.connection.meshcore.commands.set_coords(lat, lon)

            if hasattr(result, "type") and "ERROR" in str(result.type):
                self.settings_status_area.write(
                    f"[red]✗ Failed to set coordinates: {result}[/red]"
                )
            else:
                self.settings_status_area.write(
                    "[green]✓ Coordinates set successfully[/green]"
                )
                self.settings_lat_input.value = ""
                self.settings_lon_input.value = ""
        except Exception as e:
            self.logger.error(f"Error setting coordinates: {e}")
            self.settings_status_area.write(f"[red]✗ Error: {e}[/red]")

    @on(Button.Pressed, "#settings-reboot-btn")
    async def reboot_device(self) -> None:
        """Reboot the connected device."""
        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "[red]Error: Not connected to device[/red]"
                )
                return

            self.settings_status_area.write("[yellow]⚠ Rebooting device...[/yellow]")
            await self.connection.meshcore.commands.reboot()

            self.settings_status_area.write(
                "[green]✓ Reboot command sent. Device will reconnect shortly.[/green]"
            )
        except Exception as e:
            self.logger.error(f"Error rebooting device: {e}")
            self.settings_status_area.write(f"[red]✗ Error: {e}[/red]")

    @on(Button.Pressed, "#settings-battery-btn")
    async def get_battery_info(self) -> None:
        """Get battery information."""
        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "[red]Error: Not connected to device[/red]"
                )
                return

            self.settings_status_area.write("Getting battery info...")
            result = await self.connection.meshcore.commands.get_bat()

            if hasattr(result, "type") and "ERROR" in str(result.type):
                self.settings_status_area.write(
                    f"[red]✗ Failed to get battery info: {result}[/red]"
                )
            elif hasattr(result, "payload"):
                bat_info = result.payload
                voltage = bat_info.get("voltage", "N/A")
                percent = bat_info.get("percent", "N/A")
                self.settings_status_area.write(
                    f"[green]Battery: {voltage}V ({percent}%)[/green]"
                )
            else:
                self.settings_status_area.write(
                    f"[yellow]Battery info: {result}[/yellow]"
                )
        except Exception as e:
            self.logger.error(f"Error getting battery info: {e}")
            self.settings_status_area.write(f"[red]✗ Error: {e}[/red]")

    @on(Button.Pressed, "#settings-time-btn")
    async def sync_time(self) -> None:
        """Sync device time to current system time."""
        try:
            if not self.connection.is_connected():
                self.settings_status_area.write(
                    "[red]Error: Not connected to device[/red]"
                )
                return

            import time

            current_time = int(time.time())
            self.settings_status_area.write(f"Setting device time to: {current_time}")
            result = await self.connection.meshcore.commands.set_time(current_time)

            if hasattr(result, "type") and "ERROR" in str(result.type):
                self.settings_status_area.write(
                    f"[red]✗ Failed to set time: {result}[/red]"
                )
            else:
                self.settings_status_area.write(
                    "[green]✓ Device time synchronized[/green]"
                )
        except Exception as e:
            self.logger.error(f"Error syncing time: {e}")
            self.settings_status_area.write(f"[red]✗ Error: {e}[/red]")

    async def on_unmount(self) -> None:
        """Called when the app is unmounting."""
        self.logger.info("MeshTUI shutting down...")
        try:
            await self.connection.disconnect()
            self.logger.info("Connection closed successfully")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")

    def action_quit(self) -> None:
        """Override quit action to ensure proper cleanup."""
        self.logger.info("Quit action triggered")
        # Textual will call on_unmount automatically
        self.exit()

    def action_show_help(self) -> None:
        """Show help modal."""
        help_text = """
[bold cyan]MeshTUI - Quick Help[/bold cyan]

[bold yellow]Navigation:[/bold yellow]
  • Click contacts/channels to view conversations
  • Use Tab to move between input fields
  • Scroll with mouse wheel or arrow keys

[bold yellow]Messaging:[/bold yellow]
  • Type message in input field and press Enter to send
  • Direct messages: Select a contact first
  • Channel messages: Select a channel (e.g., Public)
  • Room messages: Login to room server first
  • Create channel: Click "+" button next to Channels

[bold yellow]Creating Channels:[/bold yellow]
  1. Click "+" button next to "Channels" header
  2. Enter channel slot (1-7, 0 is Public)
  3. Enter channel name (use # prefix for auto-hash)
     Example: "#mychannel" generates secret from hash
  4. Click "Create" to create the channel
  5. New channel appears in channels list

[bold yellow]Message Delivery:[/bold yellow]
  • ✓ Sent - Message transmitted successfully
  • ✓ Heard X repeats - Acknowledged by repeaters
  • ✗ Delivery failed - No response within timeout
  • Channel broadcasts show "✓ Sent (broadcast)"

[bold yellow]Node Management:[/bold yellow]
  1. Switch to Node Management tab
  2. Click "Refresh Nodes" to scan
  3. Enter node name and password
  4. Click "Login" to authenticate
  5. Use command input to send commands

[bold yellow]Keyboard Shortcuts:[/bold yellow]
  • Ctrl+C - Quit application
  • Ctrl+R - Refresh current view
  • F1 - Show this help

[bold yellow]Connection Types:[/bold yellow]
  • Direct contacts - Point-to-point messaging
  • Channels - Broadcast to all channel members
  • Room servers - BBS-style shared messaging
  • Repeaters - Extend network coverage

[bold yellow]Unread Messages:[/bold yellow]
  • Blue dot indicates unread messages
  • Messages marked as read when viewing conversation

For more information, see README.md
        """

        from textual.widgets import Label
        from textual.containers import VerticalScroll
        from textual.screen import ModalScreen

        class HelpScreen(ModalScreen):
            """Help modal screen."""

            def compose(self):
                with VerticalScroll():
                    yield Label(help_text, markup=True)

            def on_key(self, event):
                """Close on any key press."""
                self.dismiss()

        self.push_screen(HelpScreen())


def main():
    """Main entry point."""
    # Configure logging to prevent stdout output
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Allow all levels through root
    # Remove any existing handlers to prevent stdout output
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add file logging for postmortem analysis (DEBUG+)

    log_dir = Path.home() / ".config" / "meshtui"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "meshtui.log"

    # Use rotating file handler to prevent log files from growing too large
    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB per file
        backupCount=3,  # Keep 3 backup files
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Enable meshcore debug logging - force propagate and add handler
    meshcore_logger = logging.getLogger("meshcore")
    meshcore_logger.setLevel(logging.DEBUG)
    meshcore_logger.propagate = True
    meshcore_logger.addHandler(file_handler)  # Add our file handler directly
    meshcore_logger.info("Meshcore logging enabled at DEBUG level")

    # Log startup message to file
    startup_logger = logging.getLogger("meshtui.startup")
    startup_logger.info("MeshTUI starting up - all logs will be saved to %s", log_file)

    parser = argparse.ArgumentParser(
        description="MeshTUI - Textual TUI for MeshCore companion radios"
    )
    parser.add_argument(
        "-s", "--serial", help="Connect via serial port (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=115200,
        help="Serial baudrate (default: 115200)",
    )
    parser.add_argument("-t", "--tcp", help="Connect via TCP/IP hostname")
    parser.add_argument(
        "-p", "--port", type=int, default=5000, help="TCP port (default: 5000)"
    )
    parser.add_argument("-a", "--address", help="Connect via BLE address or name")

    args = parser.parse_args()

    app = MeshTUI(args)
    app.run()


if __name__ == "__main__":
    main()
